/*
 * Driver for FLSCAM CMOS Image Sensor from Aptina
 *
 * Copyright (C) 2011, Laurent Pinchart <laurent.pinchart@ideasonboard.com>
 * Copyright (C) 2011, Javier Martin <javier.martin@vista-silicon.com>
 * Copyright (C) 2011, Guennadi Liakhovetski <g.liakhovetski@gmx.de>
 *
 * Based on the MT9V032 driver and Bastian Hecht's code.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 */

#include <linux/delay.h>
#include <linux/device.h>
#include <linux/module.h>
#include <linux/i2c.h>
#include <linux/log2.h>
#include <linux/pm.h>
#include <linux/slab.h>
#include <media/v4l2-subdev.h>
#include <linux/videodev2.h>

#include <media/flscam.h>
#include <media/v4l2-chip-ident.h>
#include <media/v4l2-ctrls.h>
#include <media/v4l2-device.h>
#include <media/v4l2-subdev.h>

#define FLSCAM_PIXEL_ARRAY_WIDTH			4096
#define FLSCAM_PIXEL_ARRAY_HEIGHT			600

#define FLSCAM_PIXEL_ARRAY_WIDTH2			512
#define FLSCAM_PIXEL_ARRAY_HEIGHT2			8

#define FLSCAM_CHIP_VERSION				0x00
#define		FLSCAM_CHIP_VERSION_VALUE		0x1801
#define FLSCAM_ROW_START				0x01
#define		FLSCAM_ROW_START_MIN			0
#define		FLSCAM_ROW_START_MAX			2004
#define		FLSCAM_ROW_START_DEF			54
#define FLSCAM_COLUMN_START				0x02
#define		FLSCAM_COLUMN_START_MIN		0
#define		FLSCAM_COLUMN_START_MAX		2750
#define		FLSCAM_COLUMN_START_DEF		16
#define FLSCAM_WINDOW_HEIGHT				0x03
#define		FLSCAM_WINDOW_HEIGHT_MIN		2
#define		FLSCAM_WINDOW_HEIGHT_MAX		2006
#define		FLSCAM_WINDOW_HEIGHT_DEF		1944
#define FLSCAM_WINDOW_WIDTH				0x04
#define		FLSCAM_WINDOW_WIDTH_MIN		2
#define		FLSCAM_WINDOW_WIDTH_MAX		2752
#define		FLSCAM_WINDOW_WIDTH_DEF		2592
#define FLSCAM_HORIZONTAL_BLANK			0x05
#define		FLSCAM_HORIZONTAL_BLANK_MIN		0
#define		FLSCAM_HORIZONTAL_BLANK_MAX		4095
#define FLSCAM_VERTICAL_BLANK				0x06
#define		FLSCAM_VERTICAL_BLANK_MIN		0
#define		FLSCAM_VERTICAL_BLANK_MAX		4095
#define		FLSCAM_VERTICAL_BLANK_DEF		25
#define FLSCAM_OUTPUT_CONTROL				0x07
#define		FLSCAM_OUTPUT_CONTROL_CEN		2
#define		FLSCAM_OUTPUT_CONTROL_SYN		1
#define		FLSCAM_OUTPUT_CONTROL_DEF		0x1f82
#define FLSCAM_SHUTTER_WIDTH_UPPER			0x08
#define FLSCAM_SHUTTER_WIDTH_LOWER			0x09
#define		FLSCAM_SHUTTER_WIDTH_MIN		1
#define		FLSCAM_SHUTTER_WIDTH_MAX		1048575
#define		FLSCAM_SHUTTER_WIDTH_DEF		1943
#define	FLSCAM_PLL_CONFIG_1				0x11
#define	FLSCAM_PLL_CONFIG_2				0x12
#define FLSCAM_SHUTTER_DELAY				0x0c
#define FLSCAM_RST					0x0d
#define		FLSCAM_RST_ENABLE			1
#define		FLSCAM_RST_DISABLE			0
#define FLSCAM_READ_MODE_1				0x1e
#define FLSCAM_READ_MODE_2				0x20
#define		FLSCAM_READ_MODE_2_ROW_MIR		(1 << 15)
#define		FLSCAM_READ_MODE_2_COL_MIR		(1 << 14)
#define		FLSCAM_READ_MODE_2_ROW_BLC		(1 << 6)
#define FLSCAM_ROW_ADDRESS_MODE				0x22
#define FLSCAM_COLUMN_ADDRESS_MODE			0x23
#define FLSCAM_ROW_BLACK_DEF_OFFSET			0x4b
#define FLSCAM_TEST_PATTERN				0xa0
#define		FLSCAM_TEST_PATTERN_SHIFT		3
#define		FLSCAM_TEST_PATTERN_ENABLE		(1 << 0)
#define		FLSCAM_TEST_PATTERN_DISABLE		(0 << 0)


struct flscam_pll_divs {
	u32 ext_freq;
	u32 target_freq;
	u8 m;
	u8 n;
	u8 p1;
};

struct flscam {
	struct v4l2_subdev subdev;
	struct media_pad pad;
	struct v4l2_rect crop;  /* Sensor window */
	struct v4l2_mbus_framefmt format;
	struct v4l2_ctrl_handler ctrls;
	struct flscam_platform_data *pdata;
	struct mutex power_lock; /* lock to protect power_count */
	int power_count;
	u16 xskip;
	u16 yskip;

	const struct flscam_pll_divs *pll;

	/* Registers cache */
	u16 output_control;
	u16 mode2;
};

static struct flscam *to_flscam(struct v4l2_subdev *sd)
{
	return container_of(sd, struct flscam, subdev);
}

static int flscam_read(struct i2c_client *client, u8 reg)
{
	s32 data = i2c_smbus_read_word_data(client, reg);
	return data < 0 ? data : be16_to_cpu(data);
}

static int flscam_write(struct i2c_client *client, u8 reg, u16 data)
{
	return i2c_smbus_write_word_data(client, reg, cpu_to_be16(data));
}

static int flscam_set_output_control(struct flscam *flscam, u16 clear,
				      u16 set)
{
	struct i2c_client *client = v4l2_get_subdevdata(&flscam->subdev);
	u16 value = (flscam->output_control & ~clear) | set;
	int ret;

	ret = flscam_write(client, FLSCAM_OUTPUT_CONTROL, value);
	if (ret < 0)
		return ret;

	flscam->output_control = value;
	return 0;
}

static int flscam_set_mode2(struct flscam *flscam, u16 clear, u16 set)
{
	struct i2c_client *client = v4l2_get_subdevdata(&flscam->subdev);
	u16 value = (flscam->mode2 & ~clear) | set;
	int ret;

	ret = flscam_write(client, FLSCAM_READ_MODE_2, value);
	if (ret < 0)
		return ret;

	flscam->mode2 = value;
	return 0;
}

static int flscam_reset(struct flscam *flscam)
{
	struct i2c_client *client = v4l2_get_subdevdata(&flscam->subdev);
	int ret;

	/* Disable chip output, synchronous option update */
	ret = flscam_write(client, FLSCAM_RST, FLSCAM_RST_ENABLE);
	if (ret < 0)
		return ret;
	ret = flscam_write(client, FLSCAM_RST, FLSCAM_RST_DISABLE);
	if (ret < 0)
		return ret;

	return flscam_set_output_control(flscam, FLSCAM_OUTPUT_CONTROL_CEN,
					  0);
}

/*
 * This static table uses ext_freq and vdd_io values to select suitable
 * PLL dividers m, n and p1 which have been calculated as specifiec in p36
 * of Aptina's flscam datasheet. New values should be added here.
 */
static const struct flscam_pll_divs flscam_divs[] = {
	/* ext_freq	target_freq	m	n	p1 */
	{21000000,	48000000,	26,	2,	6}
};

static int flscam_pll_get_divs(struct flscam *flscam)
{
	struct i2c_client *client = v4l2_get_subdevdata(&flscam->subdev);
	int i;

	for (i = 0; i < ARRAY_SIZE(flscam_divs); i++) {
		if (flscam_divs[i].ext_freq == flscam->pdata->ext_freq &&
		  flscam_divs[i].target_freq == flscam->pdata->target_freq) {
			flscam->pll = &flscam_divs[i];
			return 0;
		}
	}

	dev_err(&client->dev, "Couldn't find PLL dividers for ext_freq = %d, "
		"target_freq = %d\n", flscam->pdata->ext_freq,
		flscam->pdata->target_freq);
	return -EINVAL;
}

static int flscam_pll_enable(struct flscam *flscam)
{
	struct i2c_client *client = v4l2_get_subdevdata(&flscam->subdev);
	int ret;

	ret = flscam_write(client, FLSCAM_PLL_CONTROL,
			    FLSCAM_PLL_CONTROL_PWRON);
	if (ret < 0)
		return ret;

	ret = flscam_write(client, FLSCAM_PLL_CONFIG_1,
			    (flscam->pll->m << 8) | (flscam->pll->n - 1));
	if (ret < 0)
		return ret;

	ret = flscam_write(client, FLSCAM_PLL_CONFIG_2, flscam->pll->p1 - 1);
	if (ret < 0)
		return ret;

	usleep_range(1000, 2000);
	ret = flscam_write(client, FLSCAM_PLL_CONTROL,
			    FLSCAM_PLL_CONTROL_PWRON |
			    FLSCAM_PLL_CONTROL_USEPLL);
	return ret;
}

static inline int flscam_pll_disable(struct flscam *flscam)
{
	struct i2c_client *client = v4l2_get_subdevdata(&flscam->subdev);

	return flscam_write(client, FLSCAM_PLL_CONTROL,
			     FLSCAM_PLL_CONTROL_PWROFF);
}

static int flscam_power_on(struct flscam *flscam)
{
	/* Ensure RESET_BAR is low */
	if (flscam->pdata->reset) {
		flscam->pdata->reset(&flscam->subdev, 1);
		usleep_range(1000, 2000);
	}

	/* Emable clock */
	if (flscam->pdata->set_xclk)
		flscam->pdata->set_xclk(&flscam->subdev,
					 flscam->pdata->ext_freq);

	/* Now RESET_BAR must be high */
	if (flscam->pdata->reset) {
		flscam->pdata->reset(&flscam->subdev, 0);
		usleep_range(1000, 2000);
	}

	return 0;
}

static void flscam_power_off(struct flscam *flscam)
{
	if (flscam->pdata->reset) {
		flscam->pdata->reset(&flscam->subdev, 1);
		usleep_range(1000, 2000);
	}

	if (flscam->pdata->set_xclk)
		flscam->pdata->set_xclk(&flscam->subdev, 0);
}

static int __flscam_set_power(struct flscam *flscam, bool on)
{
	struct i2c_client *client = v4l2_get_subdevdata(&flscam->subdev);
	int ret;

	if (!on) {
		flscam_power_off(flscam);
		return 0;
	}

	ret = flscam_power_on(flscam);
	if (ret < 0)
		return ret;

	ret = flscam_reset(flscam);
	if (ret < 0) {
		dev_err(&client->dev, "Failed to reset the camera\n");
		return ret;
	}

	return v4l2_ctrl_handler_setup(&flscam->ctrls);
}

/* -----------------------------------------------------------------------------
 * V4L2 subdev video operations
 */

static int flscam_set_params(struct flscam *flscam)
{
	struct i2c_client *client = v4l2_get_subdevdata(&flscam->subdev);
	struct v4l2_mbus_framefmt *format = &flscam->format;
	const struct v4l2_rect *crop = &flscam->crop;
	unsigned int hblank;
	unsigned int vblank;
	unsigned int xskip;
	unsigned int yskip;
	unsigned int xbin;
	unsigned int ybin;
	int ret;

	

	/* Row and column binning and skipping. Use the maximum binning value
	 * compatible with the skipping settings.
	 */
	xskip = DIV_ROUND_CLOSEST(crop->width, format->width);
	yskip = DIV_ROUND_CLOSEST(crop->height, format->height);
	xbin = 1 << (ffs(xskip) - 1);
	ybin = 1 << (ffs(yskip) - 1);

	ret = flscam_write(client, FLSCAM_COLUMN_ADDRESS_MODE,
			    ((xbin - 1) << 4) | (xskip - 1));
	if (ret < 0)
		return ret;
	ret = flscam_write(client, FLSCAM_ROW_ADDRESS_MODE,
			    ((ybin - 1) << 4) | (yskip - 1));
	if (ret < 0)
		return ret;

	/* Blanking - use minimum value for horizontal blanking and default
	 * value for vertical blanking.
	 */
	hblank = 346 * ybin + 64 + (80 >> max_t(unsigned int, xbin, 3));
	vblank = FLSCAM_VERTICAL_BLANK_DEF;

	ret = flscam_write(client, FLSCAM_HORIZONTAL_BLANK, hblank);
	if (ret < 0)
		return ret;
	ret = flscam_write(client, FLSCAM_VERTICAL_BLANK, vblank);
	if (ret < 0)
		return ret;

	return ret;
}

static int flscam_s_stream(struct v4l2_subdev *subdev, int enable)
{
	struct flscam *flscam = to_flscam(subdev);
	int ret;

	if (!enable) {
		/* Stop sensor readout */
		ret = flscam_set_output_control(flscam,
						 FLSCAM_OUTPUT_CONTROL_CEN, 0);
		if (ret < 0)
			return ret;

		return flscam_pll_disable(flscam);
	}

	ret = flscam_set_params(flscam);
	if (ret < 0)
		return ret;

	/* Switch to master "normal" mode */
	ret = flscam_set_output_control(flscam, 0,
					 FLSCAM_OUTPUT_CONTROL_CEN);
	if (ret < 0)
		return ret;

	return flscam_pll_enable(flscam);
}

static int flscam_enum_mbus_code(struct v4l2_subdev *subdev,
				  struct v4l2_subdev_fh *fh,
				  struct v4l2_subdev_mbus_code_enum *code)
{
	struct flscam *flscam = to_flscam(subdev);

	if (code->pad || code->index)
		return -EINVAL;

	code->code = flscam->format.code;
	return 0;
}

static int flscam_enum_frame_size(struct v4l2_subdev *subdev,
				   struct v4l2_subdev_fh *fh,
				   struct v4l2_subdev_frame_size_enum *fse)
{
	struct flscam *flscam = to_flscam(subdev);

	if (fse->index >= 8 || fse->code != flscam->format.code)
		return -EINVAL;

	fse->min_width = FLSCAM_WINDOW_WIDTH_DEF
		       / min_t(unsigned int, 7, fse->index + 1);
	fse->max_width = fse->min_width;
	fse->min_height = FLSCAM_WINDOW_HEIGHT_DEF / (fse->index + 1);
	fse->max_height = fse->min_height;

	return 0;
}

static struct v4l2_mbus_framefmt *
__flscam_get_pad_format(struct flscam *flscam, struct v4l2_subdev_fh *fh,
			 unsigned int pad, u32 which)
{
	switch (which) {
	case V4L2_SUBDEV_FORMAT_TRY:
		return v4l2_subdev_get_try_format(fh, pad);
	case V4L2_SUBDEV_FORMAT_ACTIVE:
		return &flscam->format;
	default:
		return NULL;
	}
}

static struct v4l2_rect *
__flscam_get_pad_crop(struct flscam *flscam, struct v4l2_subdev_fh *fh,
		     unsigned int pad, u32 which)
{
	switch (which) {
	case V4L2_SUBDEV_FORMAT_TRY:
		return v4l2_subdev_get_try_crop(fh, pad);
	case V4L2_SUBDEV_FORMAT_ACTIVE:
		return &flscam->crop;
	default:
		return NULL;
	}
}

static int flscam_get_format(struct v4l2_subdev *subdev,
			      struct v4l2_subdev_fh *fh,
			      struct v4l2_subdev_format *fmt)
{
	struct flscam *flscam = to_flscam(subdev);

	fmt->format = *__flscam_get_pad_format(flscam, fh, fmt->pad,
						fmt->which);
	return 0;
}

static int flscam_set_format(struct v4l2_subdev *subdev,
			      struct v4l2_subdev_fh *fh,
			      struct v4l2_subdev_format *format)
{
	struct flscam *flscam = to_flscam(subdev);
	struct v4l2_mbus_framefmt *__format;
	struct v4l2_rect *__crop;
	unsigned int width;
	unsigned int height;
	unsigned int hratio;
	unsigned int vratio;

	__crop = __flscam_get_pad_crop(flscam, fh, format->pad,
					format->which);

	/* Clamp the width and height to avoid dividing by zero. */
	width = clamp_t(unsigned int, ALIGN(format->format.width, 2),
			max(__crop->width / 7, FLSCAM_WINDOW_WIDTH_MIN),
			__crop->width);
	height = clamp_t(unsigned int, ALIGN(format->format.height, 2),
			max(__crop->height / 8, FLSCAM_WINDOW_HEIGHT_MIN),
			__crop->height);

	hratio = DIV_ROUND_CLOSEST(__crop->width, width);
	vratio = DIV_ROUND_CLOSEST(__crop->height, height);

	__format = __flscam_get_pad_format(flscam, fh, format->pad,
					    format->which);
	__format->width = __crop->width / hratio;
	__format->height = __crop->height / vratio;

	format->format = *__format;

	return 0;
}

static int flscam_get_crop(struct v4l2_subdev *subdev,
			    struct v4l2_subdev_fh *fh,
			    struct v4l2_subdev_crop *crop)
{
	struct flscam *flscam = to_flscam(subdev);

	crop->rect = *__flscam_get_pad_crop(flscam, fh, crop->pad,
					     crop->which);
	return 0;
}

static int flscam_set_crop(struct v4l2_subdev *subdev,
			    struct v4l2_subdev_fh *fh,
			    struct v4l2_subdev_crop *crop)
{
	struct flscam *flscam = to_flscam(subdev);
	struct v4l2_mbus_framefmt *__format;
	struct v4l2_rect *__crop;
	struct v4l2_rect rect;

	/* Clamp the crop rectangle boundaries and align them to a multiple of 2
	 * pixels to ensure a GRBG Bayer pattern.
	 */
	rect.left = clamp(ALIGN(crop->rect.left, 2), FLSCAM_COLUMN_START_MIN,
			  FLSCAM_COLUMN_START_MAX);
	rect.top = clamp(ALIGN(crop->rect.top, 2), FLSCAM_ROW_START_MIN,
			 FLSCAM_ROW_START_MAX);
	rect.width = clamp(ALIGN(crop->rect.width, 2),
			   FLSCAM_WINDOW_WIDTH_MIN,
			   FLSCAM_WINDOW_WIDTH_MAX);
	rect.height = clamp(ALIGN(crop->rect.height, 2),
			    FLSCAM_WINDOW_HEIGHT_MIN,
			    FLSCAM_WINDOW_HEIGHT_MAX);

	rect.width = min(rect.width, FLSCAM_PIXEL_ARRAY_WIDTH - rect.left);
	rect.height = min(rect.height, FLSCAM_PIXEL_ARRAY_HEIGHT - rect.top);

	__crop = __flscam_get_pad_crop(flscam, fh, crop->pad, crop->which);

	if (rect.width != __crop->width || rect.height != __crop->height) {
		/* Reset the output image size if the crop rectangle size has
		 * been modified.
		 */
		__format = __flscam_get_pad_format(flscam, fh, crop->pad,
						    crop->which);
		__format->width = rect.width;
		__format->height = rect.height;
	}

	*__crop = rect;
	crop->rect = rect;

	return 0;
}

/* -----------------------------------------------------------------------------
 * V4L2 subdev control operations
 */

#define V4L2_CID_TEST_PATTERN		(V4L2_CID_USER_BASE | 0x1001)

static int flscam_s_ctrl(struct v4l2_ctrl *ctrl)
{
	struct flscam *flscam =
			container_of(ctrl->handler, struct flscam, ctrls);
	struct i2c_client *client = v4l2_get_subdevdata(&flscam->subdev);
	u16 data;
	int ret;

	switch (ctrl->id) {
	case V4L2_CID_EXPOSURE:
		ret = flscam_write(client, FLSCAM_SHUTTER_WIDTH_UPPER,
				    (ctrl->val >> 16) & 0xffff);
		if (ret < 0)
			return ret;

		return flscam_write(client, FLSCAM_SHUTTER_WIDTH_LOWER,
				     ctrl->val & 0xffff);

	case V4L2_CID_GAIN:
		/* Gain is controlled by 2 analog stages and a digital stage.
		 * Valid values for the 3 stages are
		 *
		 * Stage                Min     Max     Step
		 * ------------------------------------------
		 * First analog stage   x1      x2      1
		 * Second analog stage  x1      x4      0.125
		 * Digital stage        x1      x16     0.125
		 *
		 * To minimize noise, the gain stages should be used in the
		 * second analog stage, first analog stage, digital stage order.
		 * Gain from a previous stage should be pushed to its maximum
		 * value before the next stage is used.
		 */
		if (ctrl->val <= 32) {
			data = ctrl->val;
		} else if (ctrl->val <= 64) {
			ctrl->val &= ~1;
			data = (1 << 6) | (ctrl->val >> 1);
		} else {
			ctrl->val &= ~7;
			data = ((ctrl->val - 64) << 5) | (1 << 6) | 32;
		}

		return flscam_write(client, FLSCAM_GLOBAL_GAIN, data);

	case V4L2_CID_HFLIP:
		if (ctrl->val)
			return flscam_set_mode2(flscam,
					0, FLSCAM_READ_MODE_2_COL_MIR);
		else
			return flscam_set_mode2(flscam,
					FLSCAM_READ_MODE_2_COL_MIR, 0);

	case V4L2_CID_VFLIP:
		if (ctrl->val)
			return flscam_set_mode2(flscam,
					0, FLSCAM_READ_MODE_2_ROW_MIR);
		else
			return flscam_set_mode2(flscam,
					FLSCAM_READ_MODE_2_ROW_MIR, 0);

	case V4L2_CID_TEST_PATTERN:
		if (!ctrl->val) {
			ret = flscam_set_mode2(flscam,
					0, FLSCAM_READ_MODE_2_ROW_BLC);
			if (ret < 0)
				return ret;

			return flscam_write(client, FLSCAM_TEST_PATTERN,
					     FLSCAM_TEST_PATTERN_DISABLE);
		}

		ret = flscam_write(client, FLSCAM_TEST_PATTERN_GREEN, 0x05a0);
		if (ret < 0)
			return ret;
		ret = flscam_write(client, FLSCAM_TEST_PATTERN_RED, 0x0a50);
		if (ret < 0)
			return ret;
		ret = flscam_write(client, FLSCAM_TEST_PATTERN_BLUE, 0x0aa0);
		if (ret < 0)
			return ret;

		ret = flscam_set_mode2(flscam, FLSCAM_READ_MODE_2_ROW_BLC,
					0);
		if (ret < 0)
			return ret;
		ret = flscam_write(client, FLSCAM_ROW_BLACK_DEF_OFFSET, 0);
		if (ret < 0)
			return ret;

		return flscam_write(client, FLSCAM_TEST_PATTERN,
				((ctrl->val - 1) << FLSCAM_TEST_PATTERN_SHIFT)
				| FLSCAM_TEST_PATTERN_ENABLE);
	}
	return 0;
}

static struct v4l2_ctrl_ops flscam_ctrl_ops = {
	.s_ctrl = flscam_s_ctrl,
};

static const char * const flscam_test_pattern_menu[] = {
	"Disabled",
	"Color Field",
	"Horizontal Gradient",
	"Vertical Gradient",
	"Diagonal Gradient",
	"Classic Test Pattern",
	"Walking 1s",
	"Monochrome Horizontal Bars",
	"Monochrome Vertical Bars",
	"Vertical Color Bars",
};

static const struct v4l2_ctrl_config flscam_ctrls[] = {
	{
		.ops		= &flscam_ctrl_ops,
		.id		= V4L2_CID_TEST_PATTERN,
		.type		= V4L2_CTRL_TYPE_MENU,
		.name		= "Test Pattern",
		.min		= 0,
		.max		= ARRAY_SIZE(flscam_test_pattern_menu) - 1,
		.step		= 0,
		.def		= 0,
		.flags		= 0,
		.menu_skip_mask	= 0,
		.qmenu		= flscam_test_pattern_menu,
	}
};

/* -----------------------------------------------------------------------------
 * V4L2 subdev core operations
 */

static int flscam_set_power(struct v4l2_subdev *subdev, int on)
{
	struct flscam *flscam = to_flscam(subdev);
	int ret = 0;

	mutex_lock(&flscam->power_lock);

	/* If the power count is modified from 0 to != 0 or from != 0 to 0,
	 * update the power state.
	 */
	if (flscam->power_count == !on) {
		ret = __flscam_set_power(flscam, !!on);
		if (ret < 0)
			goto out;
	}

	/* Update the power count. */
	flscam->power_count += on ? 1 : -1;
	WARN_ON(flscam->power_count < 0);

out:
	mutex_unlock(&flscam->power_lock);
	return ret;
}

/* -----------------------------------------------------------------------------
 * V4L2 subdev internal operations
 */

static int flscam_registered(struct v4l2_subdev *subdev)
{
	struct i2c_client *client = v4l2_get_subdevdata(subdev);
	struct flscam *flscam = to_flscam(subdev);
	s32 data;
	int ret;

	ret = flscam_power_on(flscam);
	if (ret < 0) {
		dev_err(&client->dev, "FLSCAM power up failed\n");
		return ret;
	}

	/* Read out the chip version register */
	data = flscam_read(client, FLSCAM_CHIP_VERSION);
	if (data != FLSCAM_CHIP_VERSION_VALUE) {
		dev_err(&client->dev, "FLSCAM not detected, wrong version "
			"0x%04x\n", data);
		return -ENODEV;
	}

	flscam_power_off(flscam);

	dev_info(&client->dev, "FLSCAM detected at address 0x%02x\n",
		 client->addr);

	return ret;
}

static int flscam_open(struct v4l2_subdev *subdev, struct v4l2_subdev_fh *fh)
{
	struct flscam *flscam = to_flscam(subdev);
	struct v4l2_mbus_framefmt *format;
	struct v4l2_rect *crop;

	crop = v4l2_subdev_get_try_crop(fh, 0);
	crop->left = FLSCAM_COLUMN_START_DEF;
	crop->top = FLSCAM_ROW_START_DEF;
	crop->width = FLSCAM_WINDOW_WIDTH_DEF;
	crop->height = FLSCAM_WINDOW_HEIGHT_DEF;

	format = v4l2_subdev_get_try_format(fh, 0);

	format->code = V4L2_MBUS_FMT_Y12_1X12;

	format->width = FLSCAM_WINDOW_WIDTH_DEF;
	format->height = FLSCAM_WINDOW_HEIGHT_DEF;
	format->field = V4L2_FIELD_NONE;
	format->colorspace = V4L2_COLORSPACE_SRGB;

	flscam->xskip = 1;
	flscam->yskip = 1;
	return flscam_set_power(subdev, 1);
}

static int flscam_close(struct v4l2_subdev *subdev, struct v4l2_subdev_fh *fh)
{
	return flscam_set_power(subdev, 0);
}

static struct v4l2_subdev_core_ops flscam_subdev_core_ops = {
	.s_power        = flscam_set_power,
};

static struct v4l2_subdev_video_ops flscam_subdev_video_ops = {
	.s_stream       = flscam_s_stream,
};

static struct v4l2_subdev_pad_ops flscam_subdev_pad_ops = {
	.enum_mbus_code = flscam_enum_mbus_code,
	.enum_frame_size = flscam_enum_frame_size,
	.get_fmt = flscam_get_format,
	.set_fmt = flscam_set_format,
	.get_crop = flscam_get_crop,
	.set_crop = flscam_set_crop,
};

static struct v4l2_subdev_ops flscam_subdev_ops = {
	.core   = &flscam_subdev_core_ops,
	.video  = &flscam_subdev_video_ops,
	.pad    = &flscam_subdev_pad_ops,
};

static const struct v4l2_subdev_internal_ops flscam_subdev_internal_ops = {
	.registered = flscam_registered,
	.open = flscam_open,
	.close = flscam_close,
};

/* -----------------------------------------------------------------------------
 * Driver initialization and probing
 */

static int flscam_probe(struct i2c_client *client,
			 const struct i2c_device_id *did)
{
	struct flscam_platform_data *pdata = client->dev.platform_data;
	struct i2c_adapter *adapter = to_i2c_adapter(client->dev.parent);
	struct flscam *flscam;
	unsigned int i;
	int ret;

	if (pdata == NULL) {
		dev_err(&client->dev, "No platform data\n");
		return -EINVAL;
	}

	if (!i2c_check_functionality(adapter, I2C_FUNC_SMBUS_WORD_DATA)) {
		dev_warn(&client->dev,
			"I2C-Adapter doesn't support I2C_FUNC_SMBUS_WORD\n");
		return -EIO;
	}

	flscam = kzalloc(sizeof(*flscam), GFP_KERNEL);
	if (flscam == NULL)
		return -ENOMEM;

	flscam->pdata = pdata;
	flscam->output_control	= FLSCAM_OUTPUT_CONTROL_DEF;
	flscam->mode2 = FLSCAM_READ_MODE_2_ROW_BLC;

	v4l2_ctrl_handler_init(&flscam->ctrls, ARRAY_SIZE(flscam_ctrls) + 4);

	v4l2_ctrl_new_std(&flscam->ctrls, &flscam_ctrl_ops,
			  V4L2_CID_EXPOSURE, FLSCAM_SHUTTER_WIDTH_MIN,
			  FLSCAM_SHUTTER_WIDTH_MAX, 1,
			  FLSCAM_SHUTTER_WIDTH_DEF);
	v4l2_ctrl_new_std(&flscam->ctrls, &flscam_ctrl_ops,
			  V4L2_CID_GAIN, FLSCAM_GLOBAL_GAIN_MIN,
			  FLSCAM_GLOBAL_GAIN_MAX, 1, FLSCAM_GLOBAL_GAIN_DEF);
	v4l2_ctrl_new_std(&flscam->ctrls, &flscam_ctrl_ops,
			  V4L2_CID_HFLIP, 0, 1, 1, 0);
	v4l2_ctrl_new_std(&flscam->ctrls, &flscam_ctrl_ops,
			  V4L2_CID_VFLIP, 0, 1, 1, 0);

	for (i = 0; i < ARRAY_SIZE(flscam_ctrls); ++i)
		v4l2_ctrl_new_custom(&flscam->ctrls, &flscam_ctrls[i], NULL);

	flscam->subdev.ctrl_handler = &flscam->ctrls;

	if (flscam->ctrls.error)
		printk(KERN_INFO "%s: control initialization error %d\n",
		       __func__, flscam->ctrls.error);

	mutex_init(&flscam->power_lock);
	v4l2_i2c_subdev_init(&flscam->subdev, client, &flscam_subdev_ops);
	flscam->subdev.internal_ops = &flscam_subdev_internal_ops;

	flscam->pad.flags = MEDIA_PAD_FL_SOURCE;
	ret = media_entity_init(&flscam->subdev.entity, 1, &flscam->pad, 0);
	if (ret < 0)
		goto done;

	flscam->subdev.flags |= V4L2_SUBDEV_FL_HAS_DEVNODE;

	flscam->crop.width = FLSCAM_WINDOW_WIDTH_DEF;
	flscam->crop.height = FLSCAM_WINDOW_HEIGHT_DEF;
	flscam->crop.left = FLSCAM_COLUMN_START_DEF;
	flscam->crop.top = FLSCAM_ROW_START_DEF;

	flscam->format.code = V4L2_MBUS_FMT_Y12_1X12;

	flscam->format.width = FLSCAM_WINDOW_WIDTH_DEF;
	flscam->format.height = FLSCAM_WINDOW_HEIGHT_DEF;
	flscam->format.field = V4L2_FIELD_NONE;
	flscam->format.colorspace = V4L2_COLORSPACE_SRGB;

	ret = flscam_pll_get_divs(flscam);

done:
	if (ret < 0) {
		v4l2_ctrl_handler_free(&flscam->ctrls);
		media_entity_cleanup(&flscam->subdev.entity);
		kfree(flscam);
	}

	return ret;
}

static int flscam_remove(struct i2c_client *client)
{
	struct v4l2_subdev *subdev = i2c_get_clientdata(client);
	struct flscam *flscam = to_flscam(subdev);

	v4l2_ctrl_handler_free(&flscam->ctrls);
	v4l2_device_unregister_subdev(subdev);
	media_entity_cleanup(&subdev->entity);
	kfree(flscam);

	return 0;
}

static const struct i2c_device_id flscam_id[] = {
	{ "flscam", 0 },
	{ }
};
MODULE_DEVICE_TABLE(i2c, flscam_id);

static struct i2c_driver flscam_i2c_driver = {
	.driver = {
		.name = "flscam",
	},
	.probe          = flscam_probe,
	.remove         = flscam_remove,
	.id_table       = flscam_id,
};

static int __init flscam_mod_init(void)
{
	return i2c_add_driver(&flscam_i2c_driver);
}

static void __exit flscam_mod_exit(void)
{
	i2c_del_driver(&flscam_i2c_driver);
}

module_init(flscam_mod_init);
module_exit(flscam_mod_exit);

MODULE_DESCRIPTION("Aptina FLSCAM Camera driver");
MODULE_AUTHOR("Bastian Hecht <hechtb@gmail.com>");
MODULE_LICENSE("GPL v2");
