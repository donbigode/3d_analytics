; sample gcode for e2e fixture
; TIME: 3600
; Filament used: 5.20m
; Material Type: PLA
; Machine Name: Test Printer
G28 ; home
G1 Z0.2 F300
G1 X10 Y10 E1 F1500
M104 S200
G1 X20 Y20 E2 F1500
M84
