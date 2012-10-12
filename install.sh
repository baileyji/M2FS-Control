#!/bin/bash
cp -rv ./etc /etc
systemctl daemon-reload
systemctl enable director.service
systemctl condrestart director.service