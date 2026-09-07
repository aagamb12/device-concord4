Concord 4 Raspberry Pi Restore Notes

Backend:
  /home/pi/device-concord4/concordsvr/concordsvr.py

Protocol library:
  /home/pi/device-concord4/concordsvr/concord/

Config:
  /home/pi/device-concord4/concordsvr/concordsvr.conf

Dashboard:
  /home/pi/concord_web.py

Systemd:
  /etc/systemd/system/concord.service
  /etc/systemd/system/concord-web.service

Serial-to-TCP:
  socket://192.168.1.250:20108

Dashboard:
  http://<PI-IP>:8080
