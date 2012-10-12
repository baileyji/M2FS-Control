#!/bin/bash
cp -r ./etc /etc
systemctl daemon-reload
systemctl enable director.service
systemctl condrestart director.service