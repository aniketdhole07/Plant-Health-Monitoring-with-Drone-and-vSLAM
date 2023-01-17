import rospy
import serial
from imu_driver.msg import imu_msg
import numpy as np

SENSOR_NAME = "imu"
rospy.init_node('imu_data')
serial_port=rospy.get_param('/driver/port')
serial_baud = rospy.get_param('~baudrate',115200)
pub = rospy.Publisher('imu', imu_msg)
msg = imu_msg()
port = serial.Serial(serial_port, serial_baud, timeout=1)
pi=22/7
port.write(b"$VNYMR, 07, 40*XX")
while(1):
    line = port.readline().decode('utf-8')
    if 'VNYMR' in str(line):
        a=str(line).split(",")
        tm=rospy.Time.now()

        #convert input degree to radian
        roll=float(a[3])*(pi/180)
        pitch=float(a[2])*(pi/180)
        yaw=float(a[1])*(pi/180)

        #convert radian to quaternion
        msg.IMU.orientation.x=np.sin(roll/2) * np.cos(pitch/2) * np.cos(yaw/2) - np.cos(roll/2) * np.sin(pitch/2) * np.sin(yaw/2)
        msg.IMU.orientation.y=np.cos(roll/2) * np.sin(pitch/2) * np.cos(yaw/2) + np.sin(roll/2) * np.cos(pitch/2) * np.sin(yaw/2)
        msg.IMU.orientation.z=np.cos(roll/2) * np.cos(pitch/2) * np.sin(yaw/2) - np.sin(roll/2) * np.sin(pitch/2) * np.cos(yaw/2)
        msg.IMU.orientation.w=np.cos(roll/2) * np.cos(pitch/2) * np.cos(yaw/2) + np.sin(roll/2) * np.sin(pitch/2) * np.sin(yaw/2)

        #angular velocity
        msg.IMU.angular_velocity.x=float(a[10])
        msg.IMU.angular_velocity.y=float(a[11])
        msg.IMU.angular_velocity.z=float(a[12].split("*")[0]) #remove checksum

        #acceleration
        msg.IMU.linear_acceleration.x=float(a[7])
        msg.IMU.linear_acceleration.y=float(a[8])
        msg.IMU.linear_acceleration.z=float(a[9])

        #magnetic field
        #msg.MagField.magnetic_field.x=float(a[4])
        #msg.MagField.magnetic_field.y=float(a[5])
        #msg.MagField.magnetic_field.z=float(a[6])

        #time and header
        #msg.Header.stamp = tm
        #msg.Header.frame_id="IMU1_Frame"

        #msg.RawData.data=str(line)
        print(msg)
        rospy.loginfo(msg)
        pub.publish(msg)
