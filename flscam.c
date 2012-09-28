/*
 * Driver for FLSCAM CMOS Image Sensor
 *
 * Copyright (C) 2012, Jeb Bailey <baileyji@umich.edu>
 * Copyright (C) 2011, Laurent Pinchart <laurent.pinchart@ideasonboard.com>
 * Copyright (C) 2011, Javier Martin <javier.martin@vista-silicon.com>
 * Copyright (C) 2011, Guennadi Liakhovetski <g.liakhovetski@gmx.de>
 *
 * Based on the MT9P031 driver.
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

#define CAM_FLD 98

#define FLSCAM_PIXEL_ARRAY_WIDTH0			4096
#define FLSCAM_PIXEL_ARRAY_HEIGHT0			600

#define FLSCAM_PIXEL_ARRAY_WIDTH1			512
#define FLSCAM_PIXEL_ARRAY_HEIGHT1			8

#define FLSCAM_CONTROL_REGISTER				0x00

//This is poorly defined because the GPIO chips starts with all as inputs
#define FLSCAM_CONTROL_REGISTER_DEFAULT			0x0000

#define FLSCAM_ENABLE					0x0001
#define FLSCAM_ONLINE					0x0002
#define	FLSCAM_TEST_PATTERN_ENABLE			0x0004
#define FLSCAM_ERRORFLAG				0x0008
#define FLSCAM_MODEBIT_0				0x0010
#define FLSCAM_MODEBIT_1				0x0020
#define FLSCAM_RESET					0x0040
#define FLSCAM_TEST2					0x0080
/* For now we'll just use all the high bits of the i2c expander */
#define FLSCAM_VERSION_BITS				0xFF00
#define		FLSCAM_VERSION_VALUE			0x0000

#define FLSCAM_MODE0					0x0000
#define FLSCAM_MODE1					0x0010
#define FLSCAM_MODE2					0x0030
#define FLSCAM_MODE3					0x0020

struct flscam {
	struct v4l2_subdev subdev;
	struct media_pad pad;
	struct v4l2_mbus_framefmt format;
	struct v4l2_ctrl_handler ctrls;
	struct flscam_platform_data *pdata;
	struct mutex power_lock; /* lock to protect power_count */
	int power_count;

	/* Registers cache */
	u16 control;
};

//OK
static struct flscam *to_flscam(struct v4l2_subdev *sd)
{
	return container_of(sd, struct flscam, subdev);
}

//OK
static int flscam_read(struct i2c_client *client, u8 reg)
{
	s32 data = i2c_smbus_read_word_data(client, reg);
	return data < 0 ? data : be16_to_cpu(data);
}

//OK
static int flscam_init_sx1503(struct i2c_client *client)
{
	const u8 data[]={0x00,0x00,0x00,0x0A};
	return i2c_smbus_write_block_data(client, 0x00, 4, data);
}

//OK
static int flscam_write(struct i2c_client *client, u8 reg, u16 data)
{
	return i2c_smbus_write_word_data(client, reg, cpu_to_be16(data));
}
//OK
static int flscam_control_clear_set(struct flscam *flscam, u16 clear,
				      u16 set)
{
	struct i2c_client *client = v4l2_get_subdevdata(&flscam->subdev);
	u16 value = (flscam->control & ~clear) | set;
	int ret;

	ret = flscam_write(client, FLSCAM_CONTROL_REGISTER, value);
	if (ret < 0)
		return ret;

	flscam->control = value;
	/* TODO: Consider checking error bit */
	return 0;
}
//OK
static int flscam_reset(struct flscam *flscam)
{
	int ret;

	ret = flscam_control_clear_set(flscam, 0xFFFF, FLSCAM_RESET);
	if (ret < 0)
		return ret;

	usleep_range(100, 200);

	ret = flscam_control_clear_set(flscam, FLSCAM_RESET, 0);
	if (ret < 0)
		return ret;

	return 0;
}
//OK
static int flscam_power_on(struct flscam *flscam)
{

	int ret;

	ret = flscam_control_clear_set(flscam, 0xFFFF, FLSCAM_RESET);
	if (ret < 0)
		return ret;

	usleep_range(100, 200);

	/* Enable clock */
	if (flscam->pdata->set_xclk)
		flscam->pdata->set_xclk(&flscam->subdev,
					 flscam->pdata->ext_freq);

	ret = flscam_control_clear_set(flscam, FLSCAM_RESET, 0);
	if (ret < 0)
		return ret;

	/*Clear reset bit and set enable bit*/
	ret = flscam_control_clear_set(flscam, FLSCAM_RESET, FLSCAM_ENABLE);
	if (ret < 0)
		return ret;

	return 0;
}
//OK
static void flscam_power_off(struct flscam *flscam)
{
	/* Clear the enable bit */
	flscam_control_clear_set(flscam, FLSCAM_ENABLE, 0);

	if (flscam->pdata->set_xclk)
		flscam->pdata->set_xclk(&flscam->subdev, 0);
}
//OK
static int __flscam_set_power(struct flscam *flscam, bool on)
{
	int ret;

	if (!on) {
		flscam_power_off(flscam);
		return 0;
	}

	ret = flscam_power_on(flscam);
	if (ret < 0)
		return ret;

	return v4l2_ctrl_handler_setup(&flscam->ctrls);
}

/* -----------------------------------------------------------------------------
 * V4L2 subdev video operations
 */

//OK
static int flscam_set_params(struct flscam *flscam)
{
	struct i2c_client *client = v4l2_get_subdevdata(&flscam->subdev);
	struct v4l2_mbus_framefmt *format = &flscam->format;
	int ret;

	//THIS FUNCTION SHOULD PROBABLY SET MODE
	if (format->width==FLSCAM_PIXEL_ARRAY_WIDTH0)
		ret= flscam_control_clear_set(flscam, FLSCAM_MODE1, FLSCAM_MODE0);
	else 
		ret= flscam_control_clear_set(flscam, FLSCAM_MODE0, FLSCAM_MODE1);

	return ret;
}
//OK 
static int flscam_s_stream(struct v4l2_subdev *subdev, int enable)
{
	struct flscam *flscam = to_flscam(subdev);
	int ret;

	if (!enable) {
		/* Stop sensor readout */
		gpio_set_value(CAM_FLD, 0);
		return 0;
	}

	ret = flscam_set_params(flscam);
	if (ret < 0)
		return ret;

	/* Start sensor readout */
	gpio_set_value(CAM_FLD, 1);

	return 0;
}
//OK
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

//OK
static int flscam_enum_frame_size(struct v4l2_subdev *subdev,
				   struct v4l2_subdev_fh *fh,
				   struct v4l2_subdev_frame_size_enum *fse)
{
	struct flscam *flscam = to_flscam(subdev);

	if (fse->index >= 2 || fse->code != flscam->format.code)
		return -EINVAL;

	if (fse->index == 0) {	
		fse->min_width = FLSCAM_PIXEL_ARRAY_WIDTH0;	
		fse->min_height = FLSCAM_PIXEL_ARRAY_HEIGHT0;
	}
	else {
		fse->min_width = FLSCAM_PIXEL_ARRAY_WIDTH1;	
		fse->min_height = FLSCAM_PIXEL_ARRAY_HEIGHT1;
	}
	fse->max_width = fse->min_width;	
	fse->max_height = fse->min_height;

	return 0;
}

//OK
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

//OK
static int flscam_get_format(struct v4l2_subdev *subdev,
			      struct v4l2_subdev_fh *fh,
			      struct v4l2_subdev_format *fmt)
{
	struct flscam *flscam = to_flscam(subdev);

	fmt->format = *__flscam_get_pad_format(flscam, fh, fmt->pad,
						fmt->which);
	return 0;
}

//OK
static int flscam_set_format(struct v4l2_subdev *subdev,
			      struct v4l2_subdev_fh *fh,
			      struct v4l2_subdev_format *format)
{
	struct flscam *flscam = to_flscam(subdev);
	struct v4l2_mbus_framefmt *__format;

	__format = __flscam_get_pad_format(flscam, fh, format->pad,
					    format->which);

	if (format->width==FLSCAM_PIXEL_ARRAY_WIDTH1) {
		__format->width = FLSCAM_PIXEL_ARRAY_WIDTH1;
		__format->height = FLSCAM_PIXEL_ARRAY_HEIGHT1;
	} else {
		__format->width = FLSCAM_PIXEL_ARRAY_WIDTH0;
		__format->height = FLSCAM_PIXEL_ARRAY_HEIGHT0;
	}
	format->format = *__format;

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

		//Do nothing for now
		return 0;

	case V4L2_CID_TEST_PATTERN:
		if (!ctrl->val) {
			return flscam_control_clear_set(flscam, FLSCAM_TEST_PATTERN_ENABLE, 0);
		}

		return flscam_control_clear_set(flscam, 0 FLSCAM_TEST_PATTERN_ENABLE);
	}
	return 0;
}

//OK
static struct v4l2_ctrl_ops flscam_ctrl_ops = {
	.s_ctrl = flscam_s_ctrl,
};

//OK
static const char * const flscam_test_pattern_menu[] = {
	"Disabled",
	"Enabled",
};

//OK
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

//OK
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

//OK
static int flscam_registered(struct v4l2_subdev *subdev)
{
	struct i2c_client *client = v4l2_get_subdevdata(subdev);
	struct flscam *flscam = to_flscam(subdev);
	s32 data;
	int ret;

	ret = flscam_power_on(flscam); //NB this starts xclka
	if (ret < 0) {
		dev_err(&client->dev, "FLSCAM power up failed\n");
		return ret;
	}

	/* Read out the chip version register */
	data = flscam_read(client, FLSCAM_CONTROL_REGISTER);
	if ((data & FLSCAM_VERSION_BITS) != FLSCAM_VERSION_VALUE) {
		dev_err(&client->dev, "FLSCAM not detected, wrong version "
			"0x%04x\n", data);
		return -ENODEV;
	}

	flscam_power_off(flscam);

	dev_info(&client->dev, "FLSCAM detected at address 0x%02x\n",
		 client->addr);

	return ret;
}

//OK
static int flscam_open(struct v4l2_subdev *subdev, struct v4l2_subdev_fh *fh)
{
	struct flscam *flscam = to_flscam(subdev);
	struct v4l2_mbus_framefmt *format;

	format = v4l2_subdev_get_try_format(fh, 0);

	format->code = V4L2_MBUS_FMT_Y8_1X8;

	//This may be superfluous 
	if (format->width==FLSCAM_PIXEL_ARRAY_WIDTH1) {
		format->width = FLSCAM_PIXEL_ARRAY_WIDTH1;
		format->height = FLSCAM_PIXEL_ARRAY_HEIGHT1;
	} else {
		format->width = FLSCAM_PIXEL_ARRAY_WIDTH0;
		format->height = FLSCAM_PIXEL_ARRAY_HEIGHT0;
	}

	format->field = V4L2_FIELD_NONE;
	format->colorspace = V4L2_COLORSPACE_SRGB;

	return flscam_set_power(subdev, 1);
}

//OK
static int flscam_close(struct v4l2_subdev *subdev, struct v4l2_subdev_fh *fh)
{
	return flscam_set_power(subdev, 0);
}

//OK
static struct v4l2_subdev_core_ops flscam_subdev_core_ops = {
	.s_power        = flscam_set_power,
};

//OK
static struct v4l2_subdev_video_ops flscam_subdev_video_ops = {
	.s_stream       = flscam_s_stream,
};

//OK
static struct v4l2_subdev_pad_ops flscam_subdev_pad_ops = {
	.enum_mbus_code = flscam_enum_mbus_code,
	.enum_frame_size = flscam_enum_frame_size,
	.get_fmt = flscam_get_format,
	.set_fmt = flscam_set_format,
};

//OK
static struct v4l2_subdev_ops flscam_subdev_ops = {
	.core   = &flscam_subdev_core_ops,
	.video  = &flscam_subdev_video_ops,
	.pad    = &flscam_subdev_pad_ops,
};

//OK
static const struct v4l2_subdev_internal_ops flscam_subdev_internal_ops = {
	.registered = flscam_registered,
	.open = flscam_open,
	.close = flscam_close,
};

/* -----------------------------------------------------------------------------
 * Driver initialization and probing
 */
//OK
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
	flscam->control	= FLSCAM_CONTROL_REGISTER_DEFAULT;

	v4l2_ctrl_handler_init(&flscam->ctrls, ARRAY_SIZE(flscam_ctrls) + 1);

	//Leaving in for now, but it does nothing
	v4l2_ctrl_new_std(&flscam->ctrls, &flscam_ctrl_ops,
			  V4L2_CID_EXPOSURE, FLSCAM_SHUTTER_WIDTH_MIN,
			  FLSCAM_SHUTTER_WIDTH_MAX, 1,
			  FLSCAM_SHUTTER_WIDTH_DEF);

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

	flscam->format.code = V4L2_MBUS_FMT_Y8_1X8;

	flscam->format.width = FLSCAM_WINDOW_WIDTH_DEF;
	flscam->format.height = FLSCAM_WINDOW_HEIGHT_DEF;
	flscam->format.field = V4L2_FIELD_NONE;
	flscam->format.colorspace = V4L2_COLORSPACE_SRGB;

	ret = flscam_init_sx1503(client);

done:
	if (ret < 0) {
		v4l2_ctrl_handler_free(&flscam->ctrls);
		media_entity_cleanup(&flscam->subdev.entity);
		kfree(flscam);
	}

	return ret;
}

//OK
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

//OK
static const struct i2c_device_id flscam_id[] = {
	{ "flscam", 0 },
	{ }
};
MODULE_DEVICE_TABLE(i2c, flscam_id);

//OK
static struct i2c_driver flscam_i2c_driver = {
	.driver = {
		.name = "flscam",
	},
	.probe          = flscam_probe,
	.remove         = flscam_remove,
	.id_table       = flscam_id,
};

//OK
static int __init flscam_mod_init(void)
{
	return i2c_add_driver(&flscam_i2c_driver);
}

//OK
static void __exit flscam_mod_exit(void)
{
	i2c_del_driver(&flscam_i2c_driver);
}

module_init(flscam_mod_init);
module_exit(flscam_mod_exit);

MODULE_DESCRIPTION("M2FS FLSCAM Camera driver");
MODULE_AUTHOR("Jeb Bailey <baileyji@umich.edu>");
MODULE_LICENSE("GPL v2");
