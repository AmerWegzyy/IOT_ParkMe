Project Name –   ParkMe		Group #12  
Short description - An IoT-based smart parking system designed for the Technion campus that detects real-time spot availability using ultrasonic sensors and enforces role-based parking permissions (Students, Lecturers, Staff) through License Plate Recognition (LPR).
User types -  
Standard User (Student/Lecturer/Staff/Special-needs-driver): Can view real-time availability based on their permit type, receive spot recommendations, and earn incentive points.
Administrator (Technion Security/Maintenance): Receives automated alerts for parking violations and monitors the system's hardware health (e.g. battery levels).

User stories 
# 
Story 
Name 
As a... 
I want... 
So that... 
1 
Availability
 Standard User
To see real-time parking availability 
I don't waste time driving in circles during peak hours.
2 
LPR Access
 Lecturer
 The system to automatically recognize my license plate
 I can park in my high-priority zone without manual verification.
3 
Violation Alert
 Administrator
 To receive a notification when an unauthorized car is detected
 I can enforce parking regulations instantly and efficiently.
4
Accessible Parking
 Special-needs Driver
 To be directed to restricted accessible parking zones
 I can easily find a suitable parking spot without checking unauthorized zones
5
 Maintenance
 Administrator
 To monitor the real-time battery life of every sensor node
 I can replace batteries before the sensor goes offline.
6
Display Access Status on Device Screen 
Standard User
the IoT device screen to clearly display either a "Welcome " message or an "Access Denied" notification when I attempt to enter 
I receive immediate, visual confirmation of my authorization status without any confusion. 
7 
Logs & Statistics
 Administrator
 To view parking usage logs over time
 I can see patterns, identify peak hours, and manage utilization
8 
Configuration
 Administrator
 To configure each sensor node to represent a specific parking category (Student, Lecturer, Staff, Accessible)
 The system can enforce the correct authorization rules for that specific spot
9 
Edge-case/Offline Handling
 Administrator
 To receive an error notification if a sensor gets disconnected from the Wi-Fi or loses power
 I can ensure the system doesn't display incorrect parking availability to users
10
Graphical User Interface (GUI) 
 Standard User
To use a dedicated web app interface
 I can easily interact with the system and check parking while on the go.
11
Calibration / Setup Mode
 Technician
To calibrate the baseline distance of the ultrasonic sensor during installation
 The system accurately detects a car regardless of the specific parking spot's physical dimensions.

 








Links to references, projects or tutorials that are related to your user stories 
# 
Relevance to our project  
(feature reference, technical reference)  
Related to user stories 
link 
1 
 Technical: Proximity detection using HC-SR04 and ESP32.
1, 6
github.com/poeticoding/parking-sensor


2 
Feature: General logic for an IoT-based smart parking system.
1, 4, 5
github.com/vishnubv944/smartParkingSystem


3 
Feature: Plate detection and recognition algorithms (LPR).
2, 3 
github.com/quangnhat185/Plate_detect_and_recognize


4 
Technical: Connecting the ESP32 to a cloud database to send and log parking history.
 8 (Logs & Statistics)
 https://github.com/Beckversync/Parking_System


5
Technical: Handling Wi-Fi disconnection and caching data locally on the ESP32.
10 (Edge-case / Offline Handling)
https://github.com/tzapu/WiFiManager


6
Technical: Creating a web server or mobile interface to configure the ESP32 parking zone.
9 (Configuration), GUI Feature
https://github.com/gemi254/ConfigAssist-ESP32-ESP8266 
7
Feature/Technical: Calibrating an ultrasonic sensor's baseline distance interactively.
Calibration Mode
https://github.com/automaticdai/esp32-ultrasonic-with-calibration



 








List of hardware we think we will need for the project  
Recommended to look at the parts catalog to see what is available 
# 
Part function 
Why we need it (optional) 
1 
ESP32 Microcontroller
Main processing unit with built-in Wi-Fi to transmit data to the cloud.
2 
Ultrasonic Sensor (HC-SR04)
To detect the physical presence of a vehicle in the parking spot.
3
ESP32-CAM Module
To capture images of license plates for the LPR authorization system.
4
Li-ion Battery
To provide wireless power to the nodes deployed in the parking lot.
5
Voltage Divider/Sensor
To monitor the battery level for the real-time health monitoring feature

 


https://docs.google.com/document/d/1thqnLOc7cXWLcVc5GZsH505tBrnMCXwP/edit