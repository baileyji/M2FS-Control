#include <linux/gpio.h>
#include <linux/regulator/machine.h>

#include <plat/i2c.h>

#include <media/flscam.h>
#include <asm/mach-types.h>
#include "devices.h"
#include "../../../drivers/media/video/omap3isp/isp.h"

#define FLSCAM_CAM_FLD_GPIO	98
#define FLSCAM_XCLK		ISP_XCLK_A
#define FLSCAM_EXT_FREQ		168000000
#define FLSCAM_I2C_ADDR		0x20

static struct regulator *reg_1v8, *reg_2v8;

static int beagle_cam_set_xclk(struct v4l2_subdev *subdev, int hz)
{
	struct isp_device *isp = v4l2_dev_to_isp_device(subdev->v4l2_dev);

	return isp->platform_cb.set_xclk(isp, hz, FLSCAM_XCLK);
}


static struct flscam_platform_data beagle_flscam_platform_data = {
	.set_xclk	= beagle_cam_set_xclk,
	.ext_freq	= FLSCAM_EXT_FREQ,
};

static struct i2c_board_info flscam_camera_i2c_device = {
	I2C_BOARD_INFO("flscam", FLSCAM_I2C_ADDR),
	.platform_data = &beagle_flscam_platform_data,
};

static struct isp_subdev_i2c_board_info flscam_camera_subdevs[] = {
	{
		.board_info = &flscam_camera_i2c_device,
		.i2c_adapter_id = 2,
	},
	{ NULL, 0, },
};
//TODO to i need to add a hsvs_syncdetect or wait_hs_vs
static struct isp_v4l2_subdevs_group beagle_camera_subdevs[] = {
	{
		.subdevs = flscam_camera_subdevs,
		.interface = ISP_INTERFACE_PARALLEL,
		.bus = {
			.parallel = {
				.data_lane_shift = 0x2, //It is 0x2 in the board file for the 2010 validation image
				.clk_pol = 1,
				.bridge = ISPCTRL_PAR_BRIDGE_DISABLE,
			}
		},
	},
	{ },
};

static struct isp_platform_data beagle_isp_platform_data = {
	.subdevs = beagle_camera_subdevs,
};

static int __init beagle_camera_init(void)
{
	if (!machine_is_omap3_beagle() || !cpu_is_omap3630())
		return 0;

	reg_1v8 = regulator_get(NULL, "cam_1v8");
	if (IS_ERR(reg_1v8))
		pr_err("%s: cannot get cam_1v8 regulator\n", __func__);
	else
		regulator_enable(reg_1v8);

	reg_2v8 = regulator_get(NULL, "cam_2v8");
	if (IS_ERR(reg_2v8))
		pr_err("%s: cannot get cam_2v8 regulator\n", __func__);
	else
		regulator_enable(reg_2v8);

	//omap_register_i2c_bus(2, 100, NULL, 0);
	gpio_request_one(FLSCAM_CAM_FLD_GPIO, GPIOF_OUT_INIT_HIGH, "cam_fld");
	omap3_init_camera(&beagle_isp_platform_data);

	return 0;
}
late_initcall(beagle_camera_init);
