import sys
import socket
import time
import boto3
import shelve
from requests import get

# Set Variables
BUFSIZE =     1024
KEY_FILE      = 'ec2_keypair.pem'    # if you need SSH access, point to your pem file here
KEY_NAME      = 'ec2_keys'           # and add KeyName=KEY_NAME 'create_instance'
IMAGE_ID      = 'ami-061392db613a6357b'
INST_TYPE     = 't2.micro'
MIN_COUNT     = 2
MAX_COUNT     = 2
VPC_CIDR      = '172.16.0.0/16'
SUBNET_CIDR   = '172.16.1.0/24'
PORT_INTERNAL = 9090
PORT_EXTERNAL = 80
LB_NAME       = 'lb1'
TARGETS_COUNT = 2
try:
    MY_IP         = get('https://api.ipify.org').text
except Exception as ip_error:
    print("Cant get my IP: ", ip_error)
    print("\nQuitting...")
    sys.exit(1)


# Check for live instances. return list with IDs
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

# Validate if resouces already exist on specified region
def validate(region):
    client = boto3.client('ec2', region_name=region)
    try:
        # Get list of live instances
        inst_id_list = get_live_instances(region)

        # Get list of existing VPCs
        vpc_response = client.describe_vpcs(Filters=[{'Name': 'tag:Name', 'Values': ['W_DEP']}])
        vpc_data = vpc_response['Vpcs']
        vpc_id = []
        for vpc in vpc_data:
            vpc_id.append(vpc['VpcId'])

        if (len(inst_id_list) > 0 ) or (len(vpc_id) > 0):
            return True, vpc_id, inst_id_list
        else:
            return False, None, None

    except Exception as err:
        print(err)
        sys.exit(1)

# Start deployment
def start(region):
    print("Checking if deployment already exist....")
    bool_val, vpc_id, inst_id_list = validate(region)
    try:
        if not bool_val:
            print("\tNothing found.. Starting deployment: \n")
            ec2_c = boto3.client('ec2', region_name=region)
            ec2 = boto3.resource('ec2', region_name=region)
            # Create VPC
            vpc = ec2.create_vpc(CidrBlock=VPC_CIDR)
            vpc.create_tags(Tags=[{"Key": "Name", "Value": "W_DEP"}])
            vpc.wait_until_available()
            print("VPC ID: ",vpc.id)

            # Create Internet Gateway
            int_gw = ec2.create_internet_gateway()
            int_gw.create_tags(Tags=[{"Key": "Name", "Value": "W_DEP"}])
            vpc.attach_internet_gateway(InternetGatewayId=int_gw.id)
            print("Internet GW ID: ",int_gw.id)

            # Create Route-Table with default route
            route_table = vpc.create_route_table()
            route_table.create_route(
                DestinationCidrBlock='0.0.0.0/0',
                GatewayId=int_gw.id
            )
            route_table.create_tags(Tags=[{"Key": "Name", "Value": "W_DEP"}])
            print("Route-Table ID: ",route_table.id)

            # Create Subnet
            subnet = ec2.create_subnet(CidrBlock=SUBNET_CIDR, VpcId=vpc.id)
            subnet.create_tags(Tags=[{"Key": "Name", "Value": "W_DEP"}])
            print("Subnet ID: ",subnet.id)

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
            print("Waiting for Instances to start... ")
            inst_waiter = ec2_c.get_waiter('instance_running')
            inst_waiter.wait(InstanceIds=id_list)
            for x in id_list:
                print("Instance ID: ",x)

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
            print("ELB DNS name: ", elb_response['DNSName'])

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

        else:
            print("\nResources Already Exist In {} Region :\n".format(region))
            print("\tInstances: \n")
            for x_id in inst_id_list:
                print(x_id)
            print("\n\tVPCs: \n")
            for z_id in vpc_id:
                print(z_id)
            print("\n\tTry 'stop', 'delete' or 'moveto' commands")
            print("Exiting...")
            sys.exit(0)
    # If error occurred during deployment, delete all
    except Exception as start_execption:
        print(start_execption)
        print("Reverting....\n")
        delete(region)


def delete(region):
    print("DELETE FUNC\n")
    # Delete EC2 Instance
    client = boto3.client('ec2',region_name=region)
    waiter_term = client.get_waiter('instance_terminated')
    response = client.describe_instances()
    inst_data = response['Reservations']
    live = []
    print("Instances:\n")
    for instances in inst_data:
        for instance in instances['Instances']:
            instance_id = instance['InstanceId']
            state = instance['State']['Name']
            if (state == 'running') or (state == 'pending'):
                live.append(instance_id)
            print("Instance: {} , State: {}".format(instance_id, state))
    for id in live:
        print("Terminating {}".format(id))
        client.terminate_instances(InstanceIds = [id])
        waiter_term.wait(InstanceIds = [id])
    print("Instances Terminated ... ")
    if len(live) > 0:
        print("Wating for 30 sec for address releasing")
        time.sleep(30)

    # Delete VPC
    vpc_response = client.describe_vpcs(Filters=[{'Name':'tag:Name', 'Values':['W_DEP']}])
    vpc_data = vpc_response['Vpcs']
    vpc_id = []
    print("\nVPCs:\n")
    for vpc in vpc_data:
        vpc_id.append(vpc['VpcId'])
        print("VPC ID: {}".format(vpc['VpcId']))

        ## Deleting All Dependencies ##
        elb_del_client = boto3.client('elb', region_name=region)
        ec2 = boto3.resource('ec2', region_name=region)
        ec2client = ec2.meta.client
        retries = 0
        try:
            # Delete ELB
            elb_del_client.delete_load_balancer(LoadBalancerName=LB_NAME)
            for v_id in vpc_id:
                print("\tDeleting ELB...")
                vpc = ec2.Vpc(v_id)
            time.sleep(2)
            # Delete Instances Subnets
            for subnet in vpc.subnets.all():
                for instance in subnet.instances.all():
                    instance.terminate()
            time.sleep(2)
            # delete network interfaces
            for subnet in vpc.subnets.all():
                for interface in subnet.network_interfaces.all():
                    print("\tDeleting Interface...")
                    interface.delete()
                print("\tDeleting Subnet...")
                subnet.delete()
            time.sleep(2)
            # Delete GW
            for gw in vpc.internet_gateways.all():
                vpc.detach_internet_gateway(InternetGatewayId=gw.id)
                print("\tDeleting GW...")
                gw.delete()
            time.sleep(2)
            # delete all route table associations
            rt_all = client.describe_route_tables(Filters=[{'Name':'tag:Name', 'Values':['W_DEP']}])
            for route_table in rt_all['RouteTables']:
                print("\tDeleting Route Table...")
                rt_id = route_table['RouteTableId']
                client.delete_route_table(RouteTableId=rt_id)

            # delete our security groups
            for sg in vpc.security_groups.all():
                if sg.group_name != 'default':
                    print("\tDeleting Security Group...")
                    sg.delete()

            # Deleting VPC
            ec2client.delete_vpc(VpcId=v_id)
        except Exception as delete_err:
            retries +=1
            if retries < 4:
                print("\n[*] Deletion encountered with errors [*]")
                print("\nTrying to run DELETE again. \nRetry {} out of 3".format(retries))
                time.sleep(2)
                delete(region)
            else:
                print("Something went wrong with deletion: ",delete_err)
                sys.exit(1)


def moveto(region):
    ec2_mv = boto3.client('ec2', region)
    ec2_lb = boto3.client('elb', region)
    # Check if deployment is already running
    print("Before moving, checking if deployment already running in current region - {}...".format(region))
    bool_val_curr, vpc_id_curr, inst_id_list_curr = validate(region)
    if not bool_val_curr:
        print("\tNo running deployment in {}, Nothing to move.".format(region))
        print("\tTry 'start' command.\nQuitting...")
        sys.exit(1)
    else:
        print("\tOk, Found running deployment\n")

    # Check if server is ready to receive commands
    print("Checking if server is ready to receive commands")
    InstanceId = []
    for id_c in inst_id_list_curr:
        InstanceId.append({'InstanceId':id_c})
    health_response = ec2_lb.describe_instance_health(
        LoadBalancerName = LB_NAME,
        Instances=InstanceId
    )
    health = []
    for state in health_response['InstanceStates']:
        if state['State'] == 'InService':
            health.append(state['InstanceId'])
    if len(health) > 0:
        print("\tOk, Service is up and running")
    else:
        print("\tService is not running. Cant send commands")
        print("\tQuitting..")
        sys.exit(1)

    # Get LB address
    dns_resp = ec2_lb.describe_load_balancers(
        LoadBalancerNames=[LB_NAME]
    )

    dns = dns_resp['LoadBalancerDescriptions'][0]['DNSName']


    # Ask user to choose destination region
    response = ec2_mv.describe_regions()
    print("\nList Of AWS Regions (Current Region Colored With RED):")
    print("-"*55+"\n")
    select = 0
    region_list = {}
    for index in response['Regions']:
        if index['RegionName'] == region:
            print('[{}]\x1b[1;31m {} \x1b[0m'.format(select, index['RegionName']))
            region_list[select]= index['RegionName']
            select += 1
        else:
            print('[{}] {}'.format(select, index['RegionName']))
            region_list[select] = index['RegionName']
            select += 1
    while True:
        choose = input("\nChoose region to move the deployment to: ")
        if int(choose) not in range(0, select+1):
            print("Invalid Input, Try Again")
        else:
            break
    move_to = region_list[int(choose)]
    print("You chose {}".format(move_to))

    # Checking for running deployment in destination region
    print("Checking if deployment already run in {}...".format(move_to))
    bool_val, vpc_id, inst_id_list = validate(move_to)
    if not bool_val:
        print("\tOk, No running deployment in {}, starting.".format(move_to))
    else:
        print("Found previous configuration... Quitting")
        sys.exit(1)

    # Sending command
    socket_response = send_command(move_to,dns, MY_IP)
    if LB_NAME in socket_response:
        print("\nSuccessfully deployed on new region. LB address:\n{}".format(socket_response))
        with shelve.open('regions', writeback=True) as db:
            db['default'] = move_to
        print("Now deleting old deployment")
        delete(region)
    else:
        print("ERR: Undefined response:")
        print(socket_response)


def send_command(move_to, dns, ip):
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conn.connect((dns, PORT_EXTERNAL))
    cmd = 'moveto {} {}'.format(move_to, ip)
    conn.send(cmd.encode())
    print("Command sent to server.. waiting for ACK")
    data = conn.recv(BUFSIZE)
    data_str = data.decode("utf-8")
    if len(data) > 0 and data_str != "error":
        return data_str
        conn.close()
    else:
        print("Something went wrong with the server")
        print("Logs located at /var/log/server.ip on the server")
        print("Quitting...")
        sys.exit(1)