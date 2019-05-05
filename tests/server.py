'''
v0.1

AWS Deployment Tool
----------------------
This is ser server part. it will listen on socket for the following commands:

stop - will remove the deployment.
moveto <region> - will initiate the same deployment in specified region

'''

import pip
import time
import sys
import socket
import logging
try:
    import boto3
except ImportError:
    pip.main(['install', 'boto3'])
    import boto3


# Set global parameters
HOST = ''
BUFSIZE       = 1024
KEY_FILE      = 'ec2_keypair.pem'
KEY_NAME      = 'ec2_keys'
#IMAGE_ID      = 'ami-061392db613a6357b'
INST_TYPE     = 't2.micro'
MIN_COUNT     = 2
MAX_COUNT     = 2
VPC_CIDR      = '172.16.0.0/16'
SUBNET_CIDR   = '172.16.1.0/24'
PORT_INTERNAL = 9090
PORT_EXTERNAL = 80
LB_NAME       = 'lb1'
TARGETS_COUNT = 2

# Set logging
logging.basicConfig(filename="/var/log/server.log", level=logging.DEBUG)

def start(region, dns):
    logging.info("'start' function starts")
    ec2_c = boto3.client('ec2', region_name=region)
    ec2 = boto3.resource('ec2', region_name=region)
    try:
        # Find ImageID in the new region
        logging.info("Checking for the AMI name in the desired region")
        img_resp = ec2_c.describe_images(
            Owners=['679593333241'],  # CentOS
            Filters=[
                {'Name': 'name', 'Values': ['CentOS Linux 7 x86_64 HVM EBS *']},
                {'Name': 'architecture', 'Values': ['x86_64']},
                {'Name': 'root-device-type', 'Values': ['ebs']},
            ],
        )
        IMAGE_ID = img_resp['Images'][0]['ImageId']

        # Create VPC
        vpc = ec2.create_vpc(CidrBlock=VPC_CIDR)
        vpc.create_tags(Tags=[{"Key": "Name", "Value": "W_DEP"}])
        vpc.wait_until_available()
        logging.info("VPC ID: ",vpc.id)

        # Create Internet Gateway
        int_gw = ec2.create_internet_gateway()
        int_gw.create_tags(Tags=[{"Key": "Name", "Value": "W_DEP"}])
        vpc.attach_internet_gateway(InternetGatewayId=int_gw.id)
        logging.info("Internet GW ID: ",int_gw.id)

        # Create Route-Table with default route
        route_table = vpc.create_route_table()
        route_table.create_route(
            DestinationCidrBlock='0.0.0.0/0',
            GatewayId=int_gw.id
        )
        route_table.create_tags(Tags=[{"Key": "Name", "Value": "W_DEP"}])
        logging.info("Route-Table ID: ",route_table.id)
        # Create Subnet
        subnet = ec2.create_subnet(CidrBlock=SUBNET_CIDR, VpcId=vpc.id)
        subnet.create_tags(Tags=[{"Key": "Name", "Value": "W_DEP"}])
        logging.info("Subnet ID: ",subnet.id)
        # Associate route table with subnet
        route_table.associate_with_subnet(SubnetId=subnet.id)
        # Create a Sec-Group
        sec_group = ec2.create_security_group(
            GroupName='W_SEC', Description='W_DEP sec group', VpcId=vpc.id)
        sec_group.authorize_ingress(
            CidrIp='0.0.0.0/0',
            IpProtocol='icmp',
            FromPort=-1,
            ToPort=-1
        )
        sec_group.authorize_ingress(
            CidrIp=MY_IP+"/32",
            IpProtocol='tcp',
            FromPort=22,
            ToPort=22
        )
        sec_group.authorize_ingress(
            CidrIp=SUBNET_CIDR,
            IpProtocol='tcp',
            FromPort=PORT_INTERNAL,
            ToPort=PORT_INTERNAL
        )
        sec_group.authorize_ingress(
            CidrIp=MY_IP + "/32",
            IpProtocol='tcp',
            FromPort=80,
            ToPort=80
        )
        sec_group.create_tags(Tags=[{"Key": "Name", "Value": "W_DEP"}])

        # Create Instance
        run_instances = ec2.create_instances(ImageId=IMAGE_ID, InstanceType=INST_TYPE,
                                                          MaxCount=MAX_COUNT, MinCount=MIN_COUNT,KeyName=KEY_NAME,
                                             NetworkInterfaces=[{
                                                 'DeviceIndex': 0,
                                                 'SubnetId': subnet.id,
                                                 'Groups': [sec_group.id],
                                                 'AssociatePublicIpAddress': True
                                             }],
                                             TagSpecifications=[{
                                                 'ResourceType': 'instance',
                                                 'Tags':[
                                                     {
                                                         'Key': 'Name',
                                                         'Value': 'W_DEP'
                                                     }
                                                 ]
                                             }],
                                             UserData=open("user-data.sh").read()
                                             )
        # Get Instance IDs
        id_list = get_live_instances(region)
        # Wait for instances to come up
        logging.info("Waiting for Instances to start... ")
        inst_waiter = ec2_c.get_waiter('instance_running')
        inst_waiter.wait(InstanceIds=id_list)
        for x in id_list:
            logging.info("Instance ID: ",x)
        # Create ELB
        elb_client =  boto3.client('elb', region_name=region)
        elb_response = elb_client.create_load_balancer(
            LoadBalancerName = LB_NAME,
            Listeners=[
                {
                    'Protocol': 'tcp',
                    'LoadBalancerPort': PORT_EXTERNAL,
                    'InstanceProtocol': 'tcp',
                    'InstancePort': PORT_INTERNAL,
                }
            ],
            Subnets=[subnet.id],
            SecurityGroups=[sec_group.id],
            Tags=[
                {
                    'Key': 'Name',
                    'Value': 'W_DEP'
                },]
        )

        dns_name = elb_response['DNSName']
        logging.info("ELB DNS name: ", dns_name)
        # Edit Healthcheck
        elb_client.configure_health_check(
            LoadBalancerName = LB_NAME,
            HealthCheck={
                'Target': 'tcp:{}'.format(PORT_INTERNAL),
                'Interval': 30,
                'Timeout': 3,
                'UnhealthyThreshold': 2,
                'HealthyThreshold': 2
            }
        )
        # Register Instances With ELB
        reg_list = []
        for i_id in id_list:
            reg_list.append({'InstanceId': i_id})
        elb_client.register_instances_with_load_balancer(
            LoadBalancerName= LB_NAME,
            Instances= reg_list
        )

        return dns_name
    except Exception as start_execption:
        logging.error(start_execption)
        logging.error("Reverting....\n")
        return False


def get_live_instances(region):
    ec2_c = boto3.client('ec2', region_name=region)
    ins_response = ec2_c.describe_instances(
        Filters=[
            {
                'Name': 'tag:Name',
                'Values': ['W_DEP']
            }
        ]
    )
    id_list = []
    for instance in ins_response['Reservations']:
        for instance_id in instance['Instances']:
            state = instance_id['State']['Name']
            in_id = instance_id['InstanceId']
            if state != 'terminated':
                id_list.append(in_id)
    return id_list


def run():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, PORT_INTERNAL))
    logging.info("\nServer started on port: %s" % PORT_INTERNAL)
    s.listen(1)
    logging.info("Now listening...\n")
    # conn = client socket
    conn, addr = s.accept()
    while True:
        logging.info('New connection from %s:%d' % (addr[0], addr[1]))
        print('New connection from %s:%d' % (addr[0], addr[1]))
        command = conn.recv(BUFSIZE)
        command_str = command.decode("utf-8")
        if not command:
            break
        # stop command
        elif command_str == 'stop':
            print(command_str)
            conn.send(command)
            conn.close()
            logging.info("Got 'stop' command")
        # moveto command
        elif "moveto" in command_str:
            region = command_str.split()[1]
            dns = command_str.split()[2]
            logging.info(recieved)
            resp = start(region, dns)
            if resp:
                conn.send(resp.encode())
            else:
                conn.send('\b0')
            conn.close()
        else:
            print(command_str)
            conn.send(command)
            conn.close()



if __name__ == "__main__":
    run()