#ifndef FLSCAM_H
#define FLSCAM_H

struct v4l2_subdev;

struct flscam_platform_data {
	int (*set_xclk)(struct v4l2_subdev *subdev, int hz);
	int (*reset)(struct v4l2_subdev *subdev, int active);
	int ext_freq; /* input frequency to the flscam */
};

#endif
