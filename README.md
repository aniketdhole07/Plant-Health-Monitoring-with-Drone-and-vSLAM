# Determination of Plant Health using NoIR Camera and Implementing vSLAM

### Project INFRA
**Team Members: :**   Aakash Singhal (singhal.aaka), Aniket Dhole(dhole.an), Rahul Kumar(kumar.rahul4), Satvik Tyagi(tyagi.sa) & Vishnu Rohit A(annadanam.v)


**ABSTRACT:**
 This project primarily focuses on determination of plant health by calculating a parameter called ‘Normalized Difference Vegetation Index’ using the captured IR images from a sensing & navigation unit. The project is implemented using a NoIR (No-Infrared) camera for determining plant health and a Stereo Camera to perform ORB-SLAM (Oriented Fast and Brief), all connected to a Raspberry Pi. The aim of the project is to create a system for tracking health conditions of plants in indoor environments such as a greenhouse, lab, etc. The initial trial was performed in Northeastern University’s campus where both live and dead plants were scanned to test our NDVI results.


# Folder Content:
1. `src/SLAM_Codes/ORB_SLAM3`: Official Repository of ORB_SLAM3 with edited changes from our side related to stereo_inertial.cc and stereo.cc files in `Examples_Old/ROS/ORB_SLAM3/src`
2. `src/SLAM_Codes/depthai`: Library package required for our Luxonis OakD Lite Stereo Camera
3. `src/SLAM_Codes/ROS_Driver/imu_driver`: Our Driver for getting IMU data published on the ORBSLAM3 imu topic. To run the code run the launch file and use the port address as input.
4. `src/SLAM_Codes/ROS_Driver/camera_driver`: Our driver for getting images from Stereo camera gettng published to `/camera/left/image_raw` and `/camera/right/image_raw`. To run just connect the camera and run the ROS launch file.
5. `src/NDVI_Codes` : Our code for No-IR Camera and Raspberry Pi for detecting plant health: `ImageNDVI.py`: For Reading Single Image and Calculating NDVI Index ,`VideoNDVI.py`: FOr Reading Live VIdeo from camera and calculating NDVI index and `fastiecm.py`: For creating a colourmap for NDVI Scale.
6. `results/SLAM_Video` : Video of implementation of ORBSLAM3 on Stereo Camera.
7. `results/NDVI_Image_Data`: Images of sample NDVI converted images of different environments.
8. `report/report.pdf`: Final Report of the whole project.
9. `report/Team_INFRA.pptx`: PPT of the First Presentation

### REFERENCES:

[1] Fahey, T.; Pham, H.; Gardi, A.; Sabatini, R.; Stefanelli, D.; Good-win, I.; Lamb, D.W. “Active and Passive Electro-Optical Sensors for Health Assessment in Food Crops” Sensors 2021, 21, 171. https://doi.org/10.3390/s21010171

[2] T. T. Sasidhar, S. K., V. M.T., S. V. and S. K.P., "Land Cover Satellite Image Classification Using NDVI and SimpleCNN," 2019 10th International Conference on Computing, Communication and Networking Technologies (ICCCNT), 2019, pp. 1-5, doi: 10.1109/ICCCNT45670.2019.8944840.

[3] David Michael Glenn & Amy Tabb (2019) “Evaluation of Five Methods to Measure Normalized Difference Vegetation Index (NDVI) in Apple and Citrus,” International Journal of Fruit Science, 19:2, 191-210, DOI: 10.1080/15538362.2018.1502720

[4] S. Chandrachary “Introduction to 3D SLAM with RTAB-Map” Accessed: Dec. 10, 2022. [Online] Available: https://shivachandrachary.medium.com/introduction-to-3d-slam-with-rtab-map

[5] R. Mur-Artal, J. M. M. Montiel, and J. D. Tardos, “ORB-SLAM: a versatile and accurate monocular SLAM system,” IEEE Transactions on Robotics, vol. 31, no. 5, pp. 1147–1163, 2015.

[6] R. Elvira, J. D. Tardos, and J. M. M. Montiel, “ORBSLAM-atlas: ´ a robust and accurate multi-map system,” in IEEE/RSJ International Conference on Intelligent Robots and Systems (IROS), 2019, pp. 6253– 6259.



