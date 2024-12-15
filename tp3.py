import boto3 # for aws
import os # for files
import paramiko # for ssh and sftp
import requests # for testing web app
from dotenv import load_dotenv # for env
import time
import mysql.connector # for mysql
import logging
import asyncio # for benchmark
import aiohttp # for benchmark
from botocore.exceptions import ClientError
import threading

# if set to true, this will build a golden image that are used by the worker instances. It is required on the first run, but once we have our AMI, it can be set to false to make the script skip this part.
build_image= True

load_dotenv()

# this provisions all required resources
def tp3(): 
    # retrieve our AWS account using .env file
    session = init_session()

    ec2 = session.client('ec2')

    # for ssh access to our instances
    key_pair_name = 'ssh-key'
    key_file_path = f'./{key_pair_name}.pem'
    create_keypair(ec2, key_pair_name, key_file_path)
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # launch our ubuntu instance from which we will create a golden image
    if build_image ==  True:
        # enable for development if there were issues in the image creation process 
        delete_all_amis(session)
        terminate_all_instances(session)

        # instance to build the image for cluster
        security_group_name="mysql_db"
        security_group_id = create_default_security_group(session, security_group_name)
        image_builder_instance_name = "manager"
        image_name = "cluster_image"
        image_builder_id = create_image_builder_if_not_exists(session, image_builder_instance_name, security_group_id, key_pair_name)
        builder_ip = get_instance_ip(ec2, image_builder_id)

        logging.info(f"Manager instance created with IP: {builder_ip}")

        # instance to build the image for proxy
        security_group_name_2="proxy"
        security_group_id_2 = create_default_security_group(session, security_group_name_2)
        image_builder_instance_name_2 = "proxy"
        image_name_2 = "proxy_image"
        image_builder_id_2 = create_image_builder_if_not_exists_t2large(session, image_builder_instance_name_2, security_group_id_2, key_pair_name)
        builder_ip_2 = get_instance_ip(ec2, image_builder_id_2)

        # instance to build the image for trusted host
        security_group_name_3="trusted_host"
        security_group_id_3 = create_default_security_group(session, security_group_name_3)
        image_builder_instance_name_3 = "trusted_host"
        image_name_3 = "trusted_host_image"
        image_builder_id_3 = create_image_builder_if_not_exists_t2large(session, image_builder_instance_name_3, security_group_id_3, key_pair_name)
        builder_ip_3 = get_instance_ip(ec2, image_builder_id_3)

        # instance to build the image for gatekeeper
        security_group_name_4="gatekeeper"
        security_group_id_4 = create_default_security_group(session, security_group_name_4)
        image_builder_instance_name_4 = "gatekeeper"
        image_name_4 = "gatekeeper_image"
        image_builder_id_4 = create_image_builder_if_not_exists_t2large(session, image_builder_instance_name_4, security_group_id_4, key_pair_name)
        builder_ip_4 = get_instance_ip(ec2, image_builder_id_4)

        # install mysql and sysbench on the instance
        COMMAND_INSTALL_SQL_SAKILA_SYSBENCH = (
                'sudo apt-get update\n'
                'sudo apt-get install net-tools -y\n'
                'sudo apt-get install python3 -y\n'
                'sudo apt-get install python3-pip -y\n'
                'sudo apt-get install python3-requests -y\n'
                'sudo apt-get install python3-mysql.connector -y\n'
                'sudo apt-get install mysql-server -y\n'
                'sudo wget "https://downloads.mysql.com/docs/sakila-db.tar.gz"\n'
                'sudo tar -xvzf sakila-db.tar.gz\n'
                'sudo mysql -e "SOURCE /home/ubuntu/sakila-db/sakila-schema.sql; SOURCE /home/ubuntu/sakila-db/sakila-data.sql; USE sakila; SHOW FULL TABLES; SELECT COUNT(*) FROM film; SELECT COUNT(*) FROM film_text;"\n'
                'sudo apt-get install sysbench -y\n'
                'sudo sysbench /usr/share/sysbench/oltp_read_only.lua --mysql-db=sakila --mysql-user="ubuntu" --mysql-password="ubuntu" prepare\n'
                'sudo sysbench /usr/share/sysbench/oltp_read_only.lua --mysql-db=sakila --mysql-user="ubuntu" --mysql-password="ubuntu" run\n'
                'sudo sed -i "s/bind-address.*/bind-address = 0.0.0.0/" /etc/mysql/mysql.conf.d/mysqld.cnf\n'
                'sudo sed -i "s/^#\s*binlog_do_db\s*=.*/binlog_do_db = sakila/" /etc/mysql/mysql.conf.d/mysqld.cnf\n'
                'sudo sed -i "s/^#\s*log_bin/log_bin/" /etc/mysql/mysql.conf.d/mysqld.cnf\n'
                "sudo systemctl restart mysql\n"
                'sudo mysql -e "USE sakila; SHOW FULL TABLES; SELECT COUNT(*) FROM film; SELECT COUNT(*) FROM film_text;"\n'
                'sudo mysql -e "CREATE USER IF NOT EXISTS \'ubuntu\'@\'%\' IDENTIFIED WITH mysql_native_password BY \'ubuntu\';"\n'
                'sudo mysql -e "GRANT ALL PRIVILEGES ON sakila.* TO \'ubuntu\'@\'%\' WITH GRANT OPTION;"\n'
                'sudo mysql -e "FLUSH PRIVILEGES;"\n'
                'sudo apt-get update\n'
            )
        ssh_and_run_command(builder_ip, key_file_path, COMMAND_INSTALL_SQL_SAKILA_SYSBENCH)

        # install flask api
        command_install_flask = (
                'sudo rm -rf /home/ubuntu/flask_app\n'  # Supprimez le répertoire flask_app s'il existe déjà
                'sudo mkdir /home/ubuntu/flask_app\n'
                'sudo chown -R ubuntu:ubuntu /home/ubuntu/flask_app\n'
                'cd /home/ubuntu/flask_app\n'
                'sudo apt-get update\n'
                'sudo apt-get install net-tools -y\n'
                'sudo apt-get install python3 -y\n'
                'sudo apt-get install python3-pip -y\n'
                'sudo apt-get install python3-venv -y\n'
                'sudo apt-get install python3-flask -y\n'
                'sudo apt-get install python3-requests -y\n'
                "sudo apt-get install mysql-server -y\n"
                'sudo apt-get install python3-mysql.connector -y\n'
                'cd /home/ubuntu/flask_app\n'
                'sudo rm -rf venv\n'
                'python3 -m venv venv\n'
                'source venv/bin/activate\n'
                'pip install flask requests mysql-connector-python\n'
                'deactivate\n'
                'sudo apt-get update\n'
            )
        
        ssh_and_run_command(builder_ip_2, key_file_path, command_install_flask)
        ssh_and_run_command(builder_ip_3, key_file_path, command_install_flask)
        ssh_and_run_command(builder_ip_4, key_file_path, command_install_flask)

        command_configure_nginx = (
        'sudo apt update -y\n'
        'sudo apt install -y nginx\n'
        'sudo apt install inetutils-ping -y\n'
        'sudo cp reverse-proxy /etc/nginx/sites-available/reverse-proxy\n'
        'sudo rm /etc/nginx/sites-enabled/default\n'
        'sudo rm /etc/nginx/sites-enabled/reverse-proxy\n'
        'sudo ln -s /etc/nginx/sites-available/reverse-proxy /etc/nginx/sites-enabled/reverse-proxy\n'
        'sudo systemctl restart nginx\n'
        'sudo nginx -t'
        'sudo systemctl reload nginx\n'
    )
        ssh_and_run_command(builder_ip_4, key_file_path, command_configure_nginx)

        # upload the files to the instances
        upload_file_to_ec2(builder_ip_2, key_file_path, "./proxy.py", "/home/ubuntu/proxy.py")
        upload_file_to_ec2(builder_ip_3, key_file_path, "./trusted_host_api.py", "/home/ubuntu/trusted_host_api.py")
        upload_file_to_ec2(builder_ip_4, key_file_path, "./gatekeeper_api.py", "/home/ubuntu/gatekeeper_api.py")
        upload_file_to_ec2(builder_ip_4, key_file_path, "./reverse-proxy", "/home/ubuntu/reverse-proxy")

        # create all the ami for the instances
        ami_id = create_ami(ec2, image_builder_id, image_name)
        wait_for_amis(ec2, [ami_id])
        ami_id = get_ami_by_name(ec2, image_name)

        ami_id_2 = create_ami(ec2, image_builder_id_2, image_name_2)
        wait_for_amis(ec2, [ami_id_2])
        ami_id_2 = get_ami_by_name(ec2, image_name_2)

        ami_id_3 = create_ami(ec2, image_builder_id_3, image_name_3)   
        wait_for_amis(ec2, [ami_id_3])
        ami_id_3 = get_ami_by_name(ec2, image_name_3)

        ami_id_4 = create_ami(ec2, image_builder_id_4, image_name_4)
        wait_for_amis(ec2, [ami_id_4])
        ami_id_4 = get_ami_by_name(ec2, image_name_4)

        terminate_all_instances(session)
    else:
        print("Skipping image creation as it is already done.")
        ami_id = get_ami_by_name(ec2, "cluster_image")
        ami_id_2 = get_ami_by_name(ec2, "proxy_image")
        ami_id_3 = get_ami_by_name(ec2, "trusted_host_image")
        ami_id_4 = get_ami_by_name(ec2, "gatekeeper_image")

    terminate_all_instances(session)
    # Create the resources for our clusters
    vpc_id = create_vpc(ec2, "tp3")
    
    # for forwarding using url
    igw_id = create_internet_gateway_if_not_exists(ec2, vpc_id)

    #elbv2 = session.client('elbv2')
    ec2_resource = session.resource('ec2')

    # Create the subnets and target groups
    subnet_1_id = get_or_create_named_subnet(ec2, vpc_id, "subnet_1", "us-east-1a", "10.0.1.0/24")

    # associate IG with public subnet only for LB
    create_route_table_associate_with_subnet(ec2, subnet_1_id, igw_id, vpc_id, "Public Route Table 1")
    modify_subnet_public_ip_if_needed(ec2, subnet_1_id)

    gatekeeper_security_group_id = create_security_group(session, security_group_name="gatekeeper", ports=[22, 80, 5000, 8000], vpc_id=vpc_id, attachWithPublicSubnet=True, userIdGroupPairId = '', CIDR_IP='0.0.0.0/0')
    trusted_host_security_group_id = create_security_group(session, security_group_name="trusted_host", ports=[22, 80, 5000, 8000], vpc_id=vpc_id, attachWithPublicSubnet=False, userIdGroupPairId = '', CIDR_IP='0.0.0.0/0')
    proxy_security_group_id = create_security_group(session, security_group_name="proxy", ports=[22, 3306, 5000, 8000, 80], vpc_id=vpc_id, attachWithPublicSubnet=False, userIdGroupPairId = '', CIDR_IP='0.0.0.0/0')
    mysql_db_security_group_id = create_security_group(session, security_group_name="mysql_db", ports=[22, 3306, 5000, 8000, 80], vpc_id=vpc_id, attachWithPublicSubnet=False, userIdGroupPairId = '', CIDR_IP='0.0.0.0/0')

    # create the instances of cluster sql
    instances_ids_1 = create_ec2_instances(ec2_resource, ami_id, f"worker1", "t2.micro", key_pair_name, mysql_db_security_group_id, subnet_1_id, '10.0.1.14', 1)
    instances_ids_2 = create_ec2_instances(ec2_resource, ami_id, f"worker2", "t2.micro", key_pair_name, mysql_db_security_group_id, subnet_1_id, '10.0.1.15', 1)
    instances_ids_3 = create_ec2_instances(ec2_resource, ami_id, f"manager", "t2.micro", key_pair_name, mysql_db_security_group_id, subnet_1_id, '10.0.1.13', 1)

    # create the instances of proxy pattern
    instances_ids_4 = create_ec2_instances(ec2_resource, ami_id_2, f"proxy", "t2.large", key_pair_name, proxy_security_group_id, subnet_1_id, '10.0.1.12', 1)

    # create the instances of gatekeeper pattern
    instances_ids_5 = create_ec2_instances(ec2_resource, ami_id_4, f"gatekeeper", "t2.large", key_pair_name, gatekeeper_security_group_id, subnet_1_id, '10.0.1.10', 1)
    instances_ids_6 = create_ec2_instances(ec2_resource, ami_id_3, f"trusted_host", "t2.large", key_pair_name, trusted_host_security_group_id, subnet_1_id, '10.0.1.11', 1)
    
    # make sure they are available before processing
    wait_for_instances_running(ec2, instances_ids_1)
    wait_for_instances_running(ec2, instances_ids_2)
    wait_for_instances_running(ec2, instances_ids_3)
    wait_for_instances_running(ec2, instances_ids_4)
    wait_for_instances_running(ec2, instances_ids_5)
    wait_for_instances_running(ec2, instances_ids_6)

    # the script might crash if instances are tagged as running but not completely booted
    print("Wait 10 more seconds for instances to boot")
    if build_image ==  True:
        time.sleep(10)
        
        if build_image ==  True:
            time.sleep(5)
            print("Wait 5 more seconds for instances to boot")
    
    # Get instance by name

    # get the ip of the instances 
    ip_worker1 = get_instance_ip(ec2, instances_ids_1[0], privateIpAddress=False)
    ip_worker2 = get_instance_ip(ec2, instances_ids_2[0], privateIpAddress=False)
    ip_manager = get_instance_ip(ec2, instances_ids_3[0], privateIpAddress=False)
    ip_proxy = get_instance_ip(ec2, instances_ids_4[0], privateIpAddress=False)
    ip_gatekeeper = get_instance_ip(ec2, instances_ids_5[0], privateIpAddress=False)
    ip_trusted_host = get_instance_ip(ec2, instances_ids_6[0], privateIpAddress=False)

    # get private ip of the instances
    private_ip_worker1 = get_instance_ip(ec2, instances_ids_1[0], privateIpAddress=True)
    private_ip_worker2 = get_instance_ip(ec2, instances_ids_2[0], privateIpAddress=True)
    private_ip_manager = get_instance_ip(ec2, instances_ids_3[0], privateIpAddress=True)
    private_ip_proxy = get_instance_ip(ec2, instances_ids_4[0], privateIpAddress=True)
    private_ip_gatekeeper = get_instance_ip(ec2, instances_ids_5[0], privateIpAddress=True)
    private_ip_trusted_host = get_instance_ip(ec2, instances_ids_6[0], privateIpAddress=True)


    # Démarrer les APIS dans un thread séparé
    def run_apis():
        def run_api_command(ip, key_file_path, command):
            ssh_and_run_command(ip, key_file_path, command)

        # Define the commands to run the APIs
        commands = [
            ('python3 /home/ubuntu/proxy.py\n', ip_proxy),
            ('python3 /home/ubuntu/trusted_host_api.py\n', ip_trusted_host),
            ('python3 /home/ubuntu/gatekeeper_api.py\n', ip_gatekeeper)
        ]

        # Create and start threads for each command
        threads = []
        for command, ip in commands:
            thread = threading.Thread(target=run_api_command, args=(ip, key_file_path, command))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

    def tp3_partie2():
        command = (
                'sudo systemctl restart mysql\n'
                "sudo mysql -e 'USE sakila; SHOW FULL TABLES;'\n"
                    )
        ssh_and_run_command(ip_worker1, key_file_path, command)
        ssh_and_run_command(ip_worker2, key_file_path, command)
        ssh_and_run_command(ip_manager, key_file_path, command)

        connection_to_db(ip_manager)
        connection_to_db(ip_worker1)
        connection_to_db(ip_worker2)

        #test_web_service_with_requests(f"http://{ip_gatekeeper}:5000/health")

        # Send 1000 requests to the gatekeeper instance
        async def benchmarks():
            await sendRequests(f"http://{ip_gatekeeper}:5000/directHit", "GET", "directHit")
            await sendRequests(f"http://{ip_gatekeeper}:5000/addfilm", "POST", "writeHit")
            await sendRequests(f"http://{ip_gatekeeper}:5000/customHit", "GET", "customHit")
            await sendRequests(f"http://{ip_gatekeeper}:5000/randomHit", "GET", "randomHit")

        # Benchmark the gatekeeper instance
        asyncio.run(benchmarks())
        print("-------> TP3 IaC script is done!") 

        # Shutdown the threads and the CLI
        os._exit(0)

    # Create a separate thread for running the APIs
    api_thread = threading.Thread(target=run_apis)
    pipeline_thread = threading.Thread(target=tp3_partie2)
    api_thread.start()
    pipeline_thread.start()
    # Wait for the API thread to complete
    api_thread.join()
    pipeline_thread.join()

def init_session():
    """Init aws boto3 session"""
    session = boto3.Session(
        aws_access_key_id=os.getenv('aws_access_key_id'),
        aws_secret_access_key=os.getenv('aws_secret_access_key'),
        aws_session_token=os.getenv('aws_session_token'),
        region_name=os.getenv('aws_default_region')
    )
    return session

def create_keypair(ec2, key_pair_name, key_file_path):
    """Check if the key file already exists"""
    if not os.path.exists(key_file_path):
        try:
            # Your code here
            pass
        except Exception as e:
            print(f"An error occurred: {e}")
            # Ricky added this check due to InvalidKeyPair.NotFound error
            try:
                ec2.describe_key_pairs(KeyNames=[key_pair_name])
                print(f"Key pair '{key_pair_name}' exists in AWS but local file is missing.")
                print(f"Deleting existing key pair '{key_pair_name}' from AWS...")
                ec2.delete_key_pair(KeyName=key_pair_name)
            except ec2.exceptions.ClientError as e:
                if e.response['Error']['Code'] != 'InvalidKeyPair.NotFound':
                    raise
            # Create a new key pair
            key_pair_response = ec2.create_key_pair(KeyName=key_pair_name)
            private_key = key_pair_response['KeyMaterial']

            # Save the private key to a .pem file
            with open(key_file_path, 'w') as key_file:
                key_file.write(private_key)
            
            # Set permissions to read-only for the owner
            os.chmod(key_file_path, 0o400)  # This sets the file permissions

            print(f"Key pair '{key_pair_name}' created and saved to '{key_file_path}'")

        except Exception as e:
            print(f"Error creating key pair: {e}")
    else:
        print(f"Key pair file already exists at '{key_file_path}'.")

def terminate_all_instances(session):
    """Terminate all EC2 instances in the specified region and wait for them to terminate."""
    ec2 = session.resource('ec2')  # Use resource instead of client
    ec2_client = session.client('ec2')  # Use client for waiters
    
    # Retrieve all instances
    instances = ec2.instances.all()
    
    # Create a list to hold instance IDs
    instance_ids = [instance.id for instance in instances]
    
    # Check if there are any instances to terminate
    if not instance_ids:
        print("No instances to terminate.")
        return
    
    # Disable termination protection for all instances
    # Ricky added the code as termination was not happening
    for instance in instances:
        try:
            if instance.state['Name'] in ['running', 'pending', 'stopping', 'stopped']:
                ec2_client.modify_instance_attribute(
                    InstanceId=instance.id,
                    DisableApiTermination={'Value': False}
                )
                print(f"Disabled termination protection for instance {instance.id}")
            else:
                print(f"Skipping termination protection disable for instance {instance.id} (state: {instance.state['Name']})")
        except Exception as e:
            print(f"Error disabling termination protection for instance {instance.id}: {e}")
    
    
    # Terminate the instances
    print(f'Terminating instances: {instance_ids}')
    ec2.instances.filter(InstanceIds=instance_ids).terminate()
    
    # Wait for the termination to complete
    waiter = ec2_client.get_waiter('instance_terminated')
    try:
        print(f"Waiting for instances {instance_ids} to terminate...")
        waiter.wait(InstanceIds=instance_ids)
        print(f"Instances {instance_ids} have been terminated.")
    except Exception as e:
        print(f"Error while waiting for instance termination: {e}")

def create_default_security_group(session, security_group_name):
    
    """Create a default security group for the default VPC."""
    ec2 = session.client('ec2')
    # Check if the security group already exists and delete it
    response = ec2.describe_security_groups(
        Filters=[{'Name': 'group-name', 'Values': [security_group_name]}]
    )
    if response['SecurityGroups']:
        security_group_id = response['SecurityGroups'][0]['GroupId']
        print(f"Security group '{security_group_name}' already exists with ID: {security_group_id}")
        response = ec2.delete_security_group(GroupId=security_group_id)
        print(f"Deleted existing security group '{security_group_name}'")

    # Create the security group
    response = ec2.create_security_group(
        GroupName=security_group_name,
        Description="description"
    )
    security_group_id = response['GroupId']
    print(f"Security group '{security_group_name}' created with ID: {security_group_id}")

    # Define the base structure for ingress permissions
    ip_permissions = [
        {
            "IpProtocol": "tcp",
            "FromPort": 22,
            "ToPort": 22,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        },
        {
            "IpProtocol": "tcp",
            "FromPort": 8000,
            "ToPort": 8000,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        },
    ]

    # Authorize the ingress permissions
    ec2.authorize_security_group_ingress(
        GroupId=security_group_id,
        IpPermissions=ip_permissions
    )
    print(f"SSH access (port 22 and 8000) has been allowed ")
    return security_group_id

    # End of create_default_security_group

def create_security_group(session, security_group_name, vpc_id="", ports='' , attachWithPublicSubnet=False, userIdGroupPairId = '', CIDR_IP=''):
    """Create a security group with SSH access."""
    ec2_client = session.client('ec2')
    cidr_ip = CIDR_IP
    try:
        # Check if the security group already exists and delete it if it does
        response = ec2_client.describe_security_groups(
            Filters=[{'Name': 'group-name', 'Values': [security_group_name]}]
        )

        if response['SecurityGroups']:
            security_group_id = response['SecurityGroups'][0]['GroupId']
            print(f"Security group '{security_group_name}' already exists with ID: {security_group_id}")
            response = ec2_client.delete_security_group(GroupId=security_group_id)
            print(f"Deleted existing security group '{security_group_name}'")

        # Create the security group, use vpc_id if not empty
        if vpc_id:
            response = ec2_client.create_security_group(
                GroupName=security_group_name,
                Description="description",
                VpcId=vpc_id
            )
            print(f"Using specific vpc {vpc_id}")
        else:
            response = ec2_client.create_security_group(
                GroupName=security_group_name,
                Description="description"
            )
            print("Using default vpc")
        security_group_id = response['GroupId']
        print(f"Security group '{security_group_name}' created with ID: {security_group_id}")

        # Define the base structure for ingress permissions
        ip_permissions = []

        # Règle ICMP
        ip_permissions.append(
            {
                "IpProtocol": "icmp",
                "FromPort": -1,
                "ToPort": -1,
                "IpRanges": [{"CidrIp": cidr_ip}],
            }
        )

        # Ajoute des règles pour chaque port
        for port in ports:
            ip_permissions.append(
                {
                    "IpProtocol": "tcp",
                    "FromPort": port,
                    "ToPort": port,
                    "IpRanges": [{"CidrIp": cidr_ip}],
                }
            )
        # For private subnets allow from public subnet and for public subnet allow all traffic
        if attachWithPublicSubnet and userIdGroupPairId:
            for permission in ip_permissions:
                permission['UserIdGroupPairs'] = [{'GroupId': userIdGroupPairId}]
                permission.pop('IpRanges', None)
        else:
            for permission in ip_permissions:
                permission['IpRanges'] = [{'CidrIp': cidr_ip}] # we can restrict it to allow specific ip addresses

        ec2_client.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=ip_permissions
        )
        print(f"SSH access port {ports} has been allowed ")
        return security_group_id
    except ClientError as e:
        print(f"Error creating security group: {e}")
        return None

#def create_security_group_if_not_exist(security_group_name, ports, vpc_id=""):
    """
    Crée un groupe de sécurité avec des règles spécifiques si celui-ci n'existe pas.

    :param security_group_name: Nom du groupe de sécurité
    :param ports: Liste des ports à autoriser
    :param vpc_id: ID du VPC où créer le groupe (vide par défaut)
    :return: ID du groupe de sécurité ou None en cas d'erreur
    """
    import boto3
    from botocore.exceptions import ClientError

    # Initialisation de la session et du client EC2
    session = boto3.Session()
    ec2_client = session.client('ec2')
    
    try:
        
        cidr_ip = "0.0.0.0/0"
        
        # Vérifie si le groupe de sécurité existe déjà
        response = ec2_client.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [security_group_name]}]
        )

        if response["SecurityGroups"]:
            security_group_id = response["SecurityGroups"][0]["GroupId"]
            print(f"Security group '{security_group_name}' already exists with ID: {security_group_id}")
            return security_group_id

        # Crée un nouveau groupe de sécurité
        response = ec2_client.create_security_group(
            GroupName=security_group_name,
            VpcId=vpc_id,
            Description="Security group created by script",
        )
        security_group_id = response["GroupId"]
        print(f"Security group '{security_group_name}' created with ID: {security_group_id}")

        ip_permissions = []

        # Règle ICMP
        ip_permissions.append(
            {
                "IpProtocol": "icmp",
                "FromPort": -1,
                "ToPort": -1,
                "IpRanges": [{"CidrIp": cidr_ip}],
            }
        )

        # Ajoute des règles pour chaque port
        for port in ports:
            ip_permissions.append(
                {
                    "IpProtocol": "tcp",
                    "FromPort": port,
                    "ToPort": port,
                    "IpRanges": [{"CidrIp": cidr_ip}],
                }
            )

        # Autorise les règles dans le groupe de sécurité
        ec2_client.authorize_security_group_ingress(
            GroupId=security_group_id, IpPermissions=ip_permissions
        )
        print(f"Access has been allowed for ports {ports} with CIDR: {cidr_ip}")
        # Modifier le subnet de l'instance
        #ec2_client.modify_instance_attribute(
            #InstanceId=
            #SecurityGroupIds=[security_group_id])
        return security_group_id
    except ClientError as e:
        print(f"Error creating security group: {e}")
        return None

def create_open_security_group(session, security_group_name, vpc_id=""):
    ec2_client = session.client('ec2')

    # Create the security group, use vpc_id if not empty
    if vpc_id:
        response = ec2_client.create_security_group(
            GroupName=security_group_name,
            Description="Open security group with all ingress and egress",
            VpcId=vpc_id
        )
        print(f"Using specific vpc {vpc_id}")
    else:
        response = ec2_client.create_security_group(
            GroupName=security_group_name,
            Description="Open security group with all ingress and egress"
        )
        print("Using default vpc")
    
    security_group_id = response['GroupId']
    print(f"Security group '{security_group_name}' created with ID: {security_group_id}")

    # Define the base structure for ingress permissions
    ingress_permissions = [
        {
            'IpProtocol': 'icmp',
            'FromPort': -1,
            'ToPort': -1,
            'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
        }
    ] + [
        {
            'IpProtocol': 'tcp',
            'FromPort': port,
            'ToPort': port,
            'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
        } for port in [22, 5000, 443, 80, 8000, 8001]
    ]

    # Add ingress rules to the security group
    try:
        ec2_client.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=ingress_permissions
        )
        print(f'Ingress Rules Added to Security Group {security_group_id}.')
    except ec2_client.exceptions.ClientError as e:
        if 'InvalidPermission.Duplicate' in str(e):
            print(f'Ingress Rules already exist in Security Group {security_group_id}.')
        else:
            raise

    # Add egress rule to allow all traffic
    try:
        ec2_client.authorize_security_group_egress(
            GroupId=security_group_id,
            IpPermissions=[
                {
                    'IpProtocol': '-1',  # -1 means all protocols
                    'FromPort': -1,
                    'ToPort': -1,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                }
            ]
        )
        print(f'Egress Rule Added to Security Group {security_group_id}.')
    except ec2_client.exceptions.ClientError as e:
        if 'InvalidPermission.Duplicate' in str(e):
            print(f'Egress Rule already exists in Security Group {security_group_id}.')
        else:
            raise

    return security_group_id

def create_image_builder_if_not_exists(session, instance_name, security_group_id, key_name):
    """Create an EC2 instance if no instance with the specified name exists."""
    ec2 = session.resource('ec2')

    # Check for instances with the specified name
    instances = list(ec2.instances.filter(
        Filters=[{'Name': 'tag:Name', 'Values': [instance_name]}]
    ))

    # Check if any instance is running or stopped
    if instances:
        for instance in instances:
            if instance.state['Name'] == 'running':
                print(f"An instance with the name '{instance_name}' is already running.")
                return instance.id  # Return the existing running instance ID
            elif instance.state['Name'] == 'stopped':
                print(f"An instance with the name '{instance_name}' is stopped. Starting it now...")
                instance.start()
                instance.wait_until_running()
                print(f"Instance {instance.id} is now running.")
                time.sleep(10)
                return instance.id  # Return the started instance ID

    # Create an EC2 instance
    try:
        print(f"Creating a new EC2 instance with the name '{instance_name}'...")
        instance = ec2.create_instances(
            ImageId='ami-0e86e20dae9224db8',
            MinCount=1,
            MaxCount=1,
            InstanceType='t2.micro',
            KeyName=key_name,
            SecurityGroupIds=[security_group_id],
            TagSpecifications=[{
                'ResourceType': 'instance',
                'Tags': [{
                    'Key': 'Name',
                    'Value': instance_name
                }]
            }]
        )
        print(f'Instance created: {instance[0].id}')
        # Wait for the instance to be running
        instance[0].wait_until_running()
        print(f"Instance {instance[0].id} is now running.")
        print("Waiting 20 seconds for boot to finish.")
        time.sleep(20)
        return instance[0].id
    except ClientError as e:
        print(f"Error creating instance: {e}")
        return None

def create_image_builder_if_not_exists_t2large(session, instance_name, security_group_id, key_name):
    """Create an EC2 instance if no instance with the specified name exists."""
    ec2 = session.resource('ec2')

    # Check for instances with the specified name
    instances = list(ec2.instances.filter(
        Filters=[{'Name': 'tag:Name', 'Values': [instance_name]}]
    ))

    # Check if any instance is running or stopped
    if instances:
        for instance in instances:
            if instance.state['Name'] == 'running':
                print(f"An instance with the name '{instance_name}' is already running.")
                return instance.id  # Return the existing running instance ID
            elif instance.state['Name'] == 'stopped':
                print(f"An instance with the name '{instance_name}' is stopped. Starting it now...")
                instance.start()
                instance.wait_until_running()
                print(f"Instance {instance.id} is now running.")
                time.sleep(10)
                return instance.id  # Return the started instance ID

    # Create an EC2 instance
    try:
        print(f"Creating a new EC2 instance with the name '{instance_name}'...")
        instance = ec2.create_instances(
            ImageId='ami-0e86e20dae9224db8',
            MinCount=1,
            MaxCount=1,
            InstanceType='t2.large',
            KeyName=key_name,
            SecurityGroupIds=[security_group_id],
            TagSpecifications=[{
                'ResourceType': 'instance',
                'Tags': [{
                    'Key': 'Name',
                    'Value': instance_name
                }]
            }]
        )
        print(f'Instance created: {instance[0].id}')
        # Wait for the instance to be running
        instance[0].wait_until_running()
        print(f"Instance {instance[0].id} is now running.")
        print("Waiting 20 seconds for boot to finish.")
        time.sleep(20)
        return instance[0].id
    except ClientError as e:
        print(f"Error creating instance: {e}")
        return None

def get_instance_ip(ec2, instance_id, privateIpAddress=False):
    """Retrieve the public IP address of an EC2 instance."""
    response = ec2.describe_instances(InstanceIds=[instance_id])
    typeOfIp = 'PublicIpAddress'
    if privateIpAddress:
        typeOfIp = 'PrivateIpAddress'
    # Check if there are reservations and instances
    if response['Reservations']:
        instances = response['Reservations'][0]['Instances']
        if instances:
            # Check if the PublicIpAddress key exists
            if typeOfIp in instances[0]:
                print(f"{typeOfIp} for instance is {instances[0][typeOfIp]}.")
                return instances[0][typeOfIp]
            else:
                print(f"No {typeOfIp} address for instance {instance_id}.")
                return None
    print(f"No instances found for instance ID {instance_id}.")
    return None

def upload_file_to_ec2(instance_ip, key_file, local_file, remote_file, user="ubuntu"):
    """Upload a file to an EC2 instance using SFTP with retries."""
    max_retries = 10
    retry_delay = 5  # seconds

    for attempt in range(max_retries):
        try:
            # Create an SSH client
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Connect to the instance
            client.connect(hostname=instance_ip, username=user, key_filename=key_file)
            logging.info(f"Connected to {instance_ip}")

            # Use SFTP to upload the file
            sftp = client.open_sftp()
            try:
                sftp.put(local_file, remote_file)
                logging.info(f"Uploaded {local_file} to {remote_file}")
                sftp.close()
                client.close()
                return  # Exit the function if the upload is successful
            except Exception as e:
                logging.error(f"Failed to upload {local_file} to {remote_file}: {e}")
                sftp.close()
                client.close()
                raise e

        except (paramiko.ssh_exception.SSHException, paramiko.ssh_exception.NoValidConnectionsError) as e:
            logging.error(f"SSH connection failed: {e}. Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
        except Exception as e:
            logging.error(f"Unexpected error: {e}. Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)

    logging.error(f"Failed to upload {local_file} to {remote_file} after {max_retries} attempts.")

def create_and_download_ip_file(ip, key_file, file_name):

    with open(file_name, 'w') as file:
        file.write(ip)
    print(f"IP address written to file: {file_name}")

    # Download the file to the local machine

def connection_to_db(instances):
    connection = mysql.connector.connect(
            host=instances,
            port=3306,
            user="ubuntu",
            password="ubuntu",
            database="sakila"
        )
    if connection.is_connected():
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM film;")
            result = cursor.fetchone()
    if connection.is_connected():
            cursor.close()
            connection.close()

# SSH into a target instance and run a command, optionally through a bastion host.
def ssh_and_run_command(target_ip, key_file, command, bastion_ip=None):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    max_retries = 10
    retry_delay = 5  # seconds

    for attempt in range(max_retries):
        try:
            if bastion_ip:
                # Connect to the bastion host
                client.connect(hostname=bastion_ip, username='ubuntu', key_filename=key_file)

                # Create an SSH tunnel through the bastion
                bastion_transport = client.get_transport()
                src_addr = (bastion_ip, 22)
                dest_addr = (target_ip, 22)
                bastion_channel = bastion_transport.open_channel("direct-tcpip", dest_addr, src_addr)

                # Connect to the target instance through the tunnel
                target_client = paramiko.SSHClient()
                target_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                target_client.connect(hostname=target_ip, username='ubuntu', key_filename=key_file, sock=bastion_channel)
            else:
                # Direct connection to the target instance
                target_client = client
                target_client.connect(hostname=target_ip, username='ubuntu', key_filename=key_file)

            # Execute the command
            stdin, stdout, stderr = target_client.exec_command(command)
            
            # Print the output
            print(f"Command output on {target_ip}:")
            for line in stdout:
                print(line.strip())

            # Print any errors
            for line in stderr:
                print(f"Error: {line.strip()}")

            break  # Exit the loop if the command was successful

        except (paramiko.ssh_exception.NoValidConnectionsError, paramiko.ssh_exception.SSHException) as e:
            print(f"SSH connection failed on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print("Max retries reached. Unable to establish SSH connection.")
                raise

        finally:
            # Close connections
            if bastion_ip and 'target_client' in locals():
                target_client.close()
            client.close()
    try:
        if bastion_ip:
            # Connect to the bastion host
            client.connect(hostname=bastion_ip, username='ubuntu', key_filename=key_file)

            # Create an SSH tunnel through the bastion
            bastion_transport = client.get_transport()
            src_addr = (bastion_ip, 22)
            dest_addr = (target_ip, 22)
            bastion_channel = bastion_transport.open_channel("direct-tcpip", dest_addr, src_addr)

            # Connect to the target instance through the tunnel
            target_client = paramiko.SSHClient()
            target_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            target_client.connect(hostname=target_ip, username='ubuntu', key_filename=key_file, sock=bastion_channel)
        else:
            # Direct connection to the target instance
            target_client = client
            target_client.connect(hostname=target_ip, username='ubuntu', key_filename=key_file)

        # Execute the command
        stdin, stdout, stderr = target_client.exec_command(command)
        
        # Print the output
        print(f"Command output on {target_ip}:")
        for line in stdout:
            print(line.strip())

        # Print any errors
        for line in stderr:
            print(f"Error: {line.strip()}")

    finally:
        # Close connections
        if bastion_ip and 'target_client' in locals():
            target_client.close()
        client.close()

def test_web_service_with_requests(url):
    try:
        response = requests.get(url)
        print("Status Code:", response.status_code)
        print("Response Body:")
        print(response.text)  # Print the response body
    except requests.exceptions.RequestException as e:
        print("Error:", e)

def delete_all_amis(session):
    """Deregister all AMIs and delete their associated snapshots."""
    ec2_client = session.client('ec2')
    
    # Describe all AMIs owned by the current account
    try:
        response = ec2_client.describe_images(Owners=['self'])
        images = response['Images']
        
        if not images:
            print("No AMIs found.")
            return
        
        for image in images:
            image_id = image['ImageId']
            print(f"Deregistering AMI: {image_id}")
            
            # Deregister the AMI
            ec2_client.deregister_image(ImageId=image_id)
            
            # Delete associated snapshots
            for block_device in image.get('BlockDeviceMappings', []):
                if 'Ebs' in block_device:
                    snapshot_id = block_device['Ebs']['SnapshotId']
                    print(f"Deleting associated snapshot: {snapshot_id}")
                    ec2_client.delete_snapshot(SnapshotId=snapshot_id)
                    
        print("All AMIs and their snapshots have been deleted.")
        
    except Exception as e:
        print(f"An error occurred: {e}")

def get_ami_by_name(ec2, ami_name):
    """
    Retrieve the ImageId of an AMI by its name.

    :param ec2: The EC2 resource or client object.
    :param ami_name: The name of the AMI to retrieve.
    :return: The ImageId if found, otherwise None.
    """
    try:
        response = ec2.describe_images(
            Filters=[{'Name': 'name', 'Values': [ami_name]}]
        )
        
        if response['Images']:
            image_id = response['Images'][0]['ImageId']
            print(f"AMI '{ami_name}' found with ImageId: {image_id}")
            return image_id
        else:
            print(f"AMI with name '{ami_name}' not found.")
            return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def create_ami(ec2, instance_id, ami_name):
    # Check if the AMI already exists
    response = ec2.describe_images(
        Filters=[{'Name': 'name', 'Values': [ami_name]}]
    )
    
    if response['Images']:
        print(f"AMI with name '{ami_name}' already exists.")
        return response['Images'][0]['ImageId']  # Return the existing AMI ID

    try:
        # Create the AMI
        response = ec2.create_image(
            InstanceId=instance_id,
            Name=ami_name,
            NoReboot=True
        )
        ami_id = response['ImageId']
        print(f"AMI created with ID: {ami_id}")
        return ami_id
    except Exception as e:
        print(f"An error occurred: {e}")

def wait_for_amis(ec2, ami_ids):
    """
    Waits for all AMIs in the provided array to become available.
    
    :param ami_ids: List of AMI IDs to wait for.
    """
    try:
        print(f"Waiting for AMIs to become available: {ami_ids}")
        waiter = ec2.get_waiter('image_available')
        waiter.wait(ImageIds=ami_ids)
        print(f"All AMIs are now available: {ami_ids}")
    except Exception as e:
        print(f"An error occurred while waiting for AMIs: {e}")

def find_ami_id(ec2_client, ami_name):
    """
    Find the AMI ID based on the provided AMI name.

    :param ec2_client: Boto3 EC2 client
    :param ami_name: Name of the AMI to search for
    :return: AMI ID if found, else None
    """
    try:
        # Describe images filtered by name
        response = ec2_client.describe_images(
            Filters=[{'Name': 'name', 'Values': [ami_name]}]
        )

        # Check if any images are returned
        if response['Images']:
            print(f"Found AMI: {response['Images'][0]['ImageId']} with name: {ami_name}")
            return response['Images'][0]['ImageId']  # Return the first found AMI ID
        else:
            print(f"No AMI found with the name: {ami_name}")
            return None

    except Exception as e:
        print(f"An error occurred while searching for AMI: {e}")
        return None

def stop_ec2_instances(ec2_client, instance_ids):
    """
    Stops the specified EC2 instances.
    
    :param ec2_client: The EC2 client to use for stopping instances.
    :param instance_ids: List of EC2 instance IDs to stop.
    :return: Response from the stop_instances call.
    """
    if isinstance(instance_ids, str):
        # If a single instance ID is passed as a string, convert it into a list
        instance_ids = [instance_ids]

    try:
        # Stop the instances
        response = ec2_client.stop_instances(InstanceIds=instance_ids)
        
        # Print the response
        print("Stopping Instances:", response)
        return response
    except Exception as e:
        print(f"An error occurred: {e}")

def terminate_ec2_instances(ec2_client, instance_ids):
    """
    Terminates the specified EC2 instances.
    
    :param instance_ids: List of EC2 instance IDs to terminate.
    :return: Response from the terminate_instances call.
    """
    if isinstance(instance_ids, str):
        # If a single instance ID is passed as a string, convert it into a list
        instance_ids = [instance_ids]

    try:
        # Terminate the instances
        response = ec2_client.terminate_instances(InstanceIds=instance_ids)
        
        # Print the response
        print("Terminating Instances:", response)
        return response
    except Exception as e:
        print(f"An error occurred: {e}")

def get_db_private_ip(self):
    """Get the private IP address of manager, worker1 & worker2."""
    ec2 = self.session.client('ec2')
    response = ec2.describe_instances(
        Filters=[
            {'Name': 'tag:Name', 'Values': ['manager']},
            {'Name': 'instance-state-name', 'Values': ['running']}
        ]
    )
    manager_ip = response['Reservations'][0]['Instances'][0]['PrivateIpAddress']

    response = ec2.describe_instances(
        Filters=[
            {'Name': 'tag:Name', 'Values': ['worker1']},
            {'Name': 'instance-state-name', 'Values': ['running']}
        ]
    )
    worker1_ip = response['Reservations'][0]['Instances'][0]['PrivateIpAddress']

    response = ec2.describe_instances(
        Filters=[
            {'Name': 'tag:Name', 'Values': ['worker2']},
            {'Name': 'instance-state-name', 'Values': ['running']}
        ]
    )
    worker2_ip = response['Reservations'][0]['Instances'][0]['PrivateIpAddress']

    return manager_ip, worker1_ip, worker2_ip

def create_vpc(ec2, name, cidr_block='10.0.0.0/16'):
    # Check for existing VPC by name
    vpcs = ec2.describe_vpcs(Filters=[{'Name': 'tag:Name', 'Values': [name]}])

    if vpcs['Vpcs']:
        vpc_id = vpcs['Vpcs'][0]['VpcId']  # Return existing VPC ID
        print(f"Vpc already exists with ID : {vpc_id}")
        return vpc_id

    # Create a new VPC if it doesn't exist
    vpc = ec2.create_vpc(CidrBlock=cidr_block)
    vpc_id = vpc['Vpc']['VpcId']
    print(f"Created new vpc with ID : {vpc_id}")
    ec2.create_tags(Resources=[vpc_id], Tags=[{'Key': 'Name', 'Value': name}])
    return vpc_id

def get_or_create_named_subnet(ec2, vpc_id, name, availability_zone, cidr_block):
    # Check for existing Subnet by name and VPC ID
    subnets = ec2.describe_subnets(Filters=[
        {'Name': 'tag:Name', 'Values': [name]},
        {'Name': 'vpc-id', 'Values': [vpc_id]}
    ])

    if subnets['Subnets']:
        print(f"Subnet '{name}' already exists with ID: {subnets['Subnets'][0]['SubnetId']}")
        return subnets['Subnets'][0]['SubnetId']  # Return existing Subnet ID

    # Create a new Subnet if it doesn't exist
    subnet = ec2.create_subnet(CidrBlock=cidr_block, VpcId=vpc_id, AvailabilityZone=availability_zone)
    subnet_id = subnet['Subnet']['SubnetId']
    ec2.create_tags(Resources=[subnet_id], Tags=[{'Key': 'Name', 'Value': name}])
    print(f"Created new subnet '{name}' with ID: {subnet_id}")
    return subnet_id

def create_target_group(elbv2_client, vpc_id, target_group_name, port=8000):
    """Create a target group if it doesn't already exist."""
    try:
        # Check if the target group already exists
        response = elbv2_client.describe_target_groups(
            Names=[target_group_name]
        )
        if response['TargetGroups']:
            target_group_arn = response['TargetGroups'][0]['TargetGroupArn']
            print(f"Target group '{target_group_name}' already exists with ARN: {target_group_arn}")
            return target_group_arn
    except elbv2_client.exceptions.TargetGroupNotFoundException:
        # Proceed to create the target group if not found
        pass

    # Create the target group if not found
    response = elbv2_client.create_target_group(
        Name=target_group_name,
        Protocol='HTTP',
        Port=port,
        VpcId=vpc_id,
        TargetType='instance'
    )
    target_group_arn = response['TargetGroups'][0]['TargetGroupArn']
    print(f"Target group '{target_group_name}' created with ARN: {target_group_arn}")
    return target_group_arn

def create_ec2_instances(ec2_resource, ami_id, instance_name, instance_type, key_name, security_group_id, subnet_id, privateIP='', num_instances=''):
    """Create EC2 instances with a specific name tag if they don't already exist."""
    
    # Check if instances with the given name tag already exist
    instances = ec2_resource.instances.filter(
        Filters=[
            {'Name': 'tag:Name', 'Values': [instance_name]},  # Filter by name tag
            {'Name': 'instance-state-name', 'Values': ['running', 'pending']}
        ]
    )
    existing_instances = [instance.id for instance in instances]
    
    if existing_instances:
        print(f"EC2 instances with name '{instance_name}' already exist with IDs: {existing_instances}")
        return existing_instances

    # Create the EC2 instances if they don't exist
    instances = ec2_resource.create_instances(
        ImageId=ami_id,
        InstanceType=instance_type,
        KeyName=key_name,
        MinCount=num_instances,
        MaxCount=num_instances,
        NetworkInterfaces=[{
            'SubnetId': subnet_id,
            'PrivateIpAddress': privateIP,
            'DeviceIndex': 0,
            'AssociatePublicIpAddress': True,
            'Groups': [security_group_id]
        }],
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [{'Key': 'Name', 'Value': instance_name}]
            }
        ]
    )
    instance_ids = [instance.id for instance in instances]
    print(f"Created {len(instance_ids)} EC2 instances with name '{instance_name}' and IDs: {instance_ids}")
    return instance_ids

def register_targets(elbv2_client, target_group_arn, instance_ids):
    """Register EC2 instances to a target group, checking if they are already registered."""
    # Get the currently registered targets
    response = elbv2_client.describe_target_health(TargetGroupArn=target_group_arn)
    registered_instances = [target['Target']['Id'] for target in response['TargetHealthDescriptions']]
    
    # Find instances that are not already registered
    instances_to_register = [instance_id for instance_id in instance_ids if instance_id not in registered_instances]

    if not instances_to_register:
        print(f"All instances {instance_ids} are already registered to Target Group {target_group_arn}")
        return
    
    # Register the instances that are not already registered
    targets = [{'Id': instance_id} for instance_id in instances_to_register]
    elbv2_client.register_targets(
        TargetGroupArn=target_group_arn,
        Targets=targets
    )
    print(f"Registered instances {instances_to_register} to Target Group {target_group_arn}")

def create_internet_gateway_if_not_exists(ec2_client, vpc_id):
    try:
        # Check if an IGW already exists for the VPC
        existing_igws = ec2_client.describe_internet_gateways(
            Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}]
        )['InternetGateways']

        if existing_igws:
            igw_id = existing_igws[0]['InternetGatewayId']
            print(f"Internet Gateway already exists with ID: {igw_id}")
        else:
            # Create a new IGW
            response = ec2_client.create_internet_gateway()
            igw_id = response['InternetGateway']['InternetGatewayId']
            print(f"Created Internet Gateway with ID: {igw_id}")

            # Attach the IGW to the VPC
            ec2_client.attach_internet_gateway(
                InternetGatewayId=igw_id,
                VpcId=vpc_id
            )
            print(f"Attached Internet Gateway {igw_id} to VPC {vpc_id}")

        return igw_id

    except Exception as e:
        print(f"Error checking/creating Internet Gateway: {e}")

def get_route_table_for_subnet(ec2_client, subnet_id, vpc_id):
    try:
        # Try to get the route table associated with the subnet
        route_tables = ec2_client.describe_route_tables(
            Filters=[{
                'Name': 'association.subnet-id',
                'Values': [subnet_id]
            }]
        )['RouteTables']

        # If a route table is found for the subnet, return it
        if route_tables:
            return route_tables[0]['RouteTableId']

        # If no route table is found, get the main route table for the VPC
        print(f"No specific route table found for subnet {subnet_id}. Fetching the main route table for the VPC.")
        route_tables = ec2_client.describe_route_tables(
            Filters=[{
                'Name': 'vpc-id',
                'Values': [vpc_id]
            }]
        )['RouteTables']

        # Find the main route table (associated with the VPC and no specific subnet)
        for route_table in route_tables:
            for association in route_table.get('Associations', []):
                if association.get('Main'):
                    return route_table['RouteTableId']

        # If no route table found, return an error
        raise Exception(f"No route table found for subnet {subnet_id} or VPC {vpc_id}")

    except Exception as e:
        print(f"Error getting route table for subnet: {e}")
        return None

def create_route_table_associate_with_subnet(ec2_client, subnet_id, internet_gateway_id, vpc_id, name):
    # Check if a route table with the given name already exists
    existing_route_tables = ec2_client.describe_route_tables(
        Filters=[
            {'Name': 'tag:Name', 'Values': [name]},
            {'Name': 'vpc-id', 'Values': [vpc_id]}
        ]
    )['RouteTables']

    if existing_route_tables:
        rt_id = existing_route_tables[0]['RouteTableId']
        print(f"Route Table '{name}' already exists with ID: {rt_id}")
    else:
        # Create a new route table
        route_table = ec2_client.create_route_table(VpcId=vpc_id)
        rt_id = route_table['RouteTable']['RouteTableId']
        ec2_client.create_tags(Resources=[rt_id], Tags=[{'Key': 'Name', 'Value': name}])
        print(f"Route Table '{name}' created with ID: {rt_id}")

    # Check if the route to the internet gateway already exists
    routes = ec2_client.describe_route_tables(RouteTableIds=[rt_id])['RouteTables'][0]['Routes']
    igw_route_exists = any(route.get('GatewayId') == internet_gateway_id for route in routes)

    if not igw_route_exists:
        # Create route to the internet gateway
        try:
            ec2_client.create_route(
                RouteTableId=rt_id,
                DestinationCidrBlock='0.0.0.0/0',
                GatewayId=internet_gateway_id
            )
            print(f"Route to Internet Gateway {internet_gateway_id} created in Route Table {rt_id}")
        except ec2_client.exceptions.ClientError as e:
            if 'RouteAlreadyExists' in str(e):
                print(f"Route to 0.0.0.0/0 already exists in Route Table {rt_id}")
            else:
                raise

    # Check if the route table is already associated with the subnet
    associations = ec2_client.describe_route_tables(RouteTableIds=[rt_id])['RouteTables'][0]['Associations']
    subnet_associated = any(assoc['SubnetId'] == subnet_id for assoc in associations)

    if not subnet_associated:
        # Associate Route Table with Subnet
        ec2_client.associate_route_table(RouteTableId=rt_id, SubnetId=subnet_id)
        print(f"Route Table {rt_id} associated with Subnet {subnet_id}")
    else:
        print(f"Route Table {rt_id} is already associated with Subnet {subnet_id}")

    return rt_id

def modify_subnet_public_ip_if_needed(ec2_client, subnet_id, auto_assign=True):
    try:
        # Check if public IP assignment is already enabled
        current_attribute = ec2_client.describe_subnets(SubnetIds=[subnet_id])['Subnets'][0]['MapPublicIpOnLaunch']
        
        if current_attribute == auto_assign:
            print(f"Auto-assign public IP is already set to {auto_assign} for subnet {subnet_id}")
        else:
            # Modify the subnet to auto-assign public IPs
            ec2_client.modify_subnet_attribute(
                SubnetId=subnet_id,
                MapPublicIpOnLaunch={'Value': auto_assign}
            )
            print(f"Set auto-assign public IP for subnet {subnet_id} to {auto_assign}")
    
    except Exception as e:
        print(f"Error modifying subnet public IP settings: {e}")

def create_application_load_balancer(elbv2_client, name, subnets, security_group_id, vpc_id):
    """Create an Application Load Balancer if it doesn't already exist."""
    try:
        response = elbv2_client.describe_load_balancers(Names=[name])
        load_balancer_arn = response['LoadBalancers'][0]['LoadBalancerArn']
        print(f"Load balancer '{name}' already exists with ARN: {load_balancer_arn}")
        return load_balancer_arn
    except elbv2_client.exceptions.LoadBalancerNotFoundException:
        # Proceed to create the load balancer if not found
        pass

    response = elbv2_client.create_load_balancer(
        Name=name,
        Subnets=subnets,
        SecurityGroups=[security_group_id],
        Scheme='internet-facing'
    )
    load_balancer_arn = response['LoadBalancers'][0]['LoadBalancerArn']
    print(f"Load balancer '{name}' created with ARN: {load_balancer_arn}")
    
    while True:
        try:
            response = elbv2_client.describe_load_balancers(LoadBalancerArns=[load_balancer_arn])
            load_balancer = response['LoadBalancers'][0]

            # Check the state of the load balancer
            if load_balancer['State']['Code'] == 'active':
                print(f"Load balancer {load_balancer_arn} is now active.")
                break
            else:
                print(f"Current state of load balancer {load_balancer_arn}: {load_balancer['State']['Code']}. Waiting...")
        
        except ClientError as e:
            print(f"Error retrieving load balancer state: {e}")
            break

        time.sleep(5)
    
    return load_balancer_arn

def add_port_rule_to_security_group(ec2, security_group_id, port, cidr_ip='0.0.0.0/0'):
    """
    Add a rule to the specified security group to allow TCP traffic on port 8001.
    
    :param security_group_id: The ID of the security group to modify.
    :param cidr_ip: The CIDR IP range to allow (e.g., '0.0.0.0/0').
    """

    try:
        # Define the rule
        ip_permissions = [
            {
                'IpProtocol': 'tcp',
                'FromPort': port,
                'ToPort': port,
                'IpRanges': [{'CidrIp': cidr_ip}]
            }
        ]

        # Add the rule to the security group
        response = ec2.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=ip_permissions
        )
        print(f"Rule added to security group {security_group_id}: {response}")

    except ClientError as e:
        print(f"Error adding rule to security group: {e}")

def create_listener_if_not_exists(elbv2_client, load_balancer_arn, port):
    """Create a listener for the ALB if it doesn't already exist and add a path-based routing rule."""
    try:
        # Check existing listeners for the load balancer
        listeners_response = elbv2_client.describe_listeners(LoadBalancerArn=load_balancer_arn)
        
        listener_arn = None
        for listener in listeners_response['Listeners']:
            if listener['Port'] == port:
                print(f"Listener on port {port} already exists with ARN: {listener['ListenerArn']}")
                listener_arn = listener['ListenerArn']
                break
        
        # If no existing listener found, create one
        if listener_arn is None:
            response = elbv2_client.create_listener(
                LoadBalancerArn=load_balancer_arn,
                Port=port,
                Protocol='HTTP',
                DefaultActions=[{
                    'Type': 'forward',
                    'TargetGroupArn': target_group_arn,
                }]
            )
            listener_arn = response['Listeners'][0]['ListenerArn']
            print(f"Listener created on port {port} with ARN: {listener_arn}")

        # Now create or check the path-based routing rule
        create_or_update_path_based_rule(elbv2_client, listener_arn, target_group_arn, path_pattern)

        return listener_arn

    except Exception as e:
        print(f"Error creating listener or path rule: {e}")
        return None

def create_or_update_path_based_rule(elbv2_client, listener_arn, target_group_arn, path_pattern):
    """Create or update a path-based routing rule for the specified listener."""
    try:
        # Check existing rules for the listener
        rules_response = elbv2_client.describe_rules(ListenerArn=listener_arn)
        
        for rule in rules_response['Rules']:
            # Check if the rule for the specified path pattern already exists
            for condition in rule['Conditions']:
                if condition['Field'] == 'path-pattern' and path_pattern in condition['Values']:
                    print(f"Path-based rule for '{path_pattern}' already exists on listener ARN: {listener_arn}")
                    return  # Exit if the rule already exists

        # If the rule does not exist, create it
        elbv2_client.create_rule(
            ListenerArn=listener_arn,
            Conditions=[{
                'Field': 'path-pattern',
                'Values': [path_pattern]  # Use the passed path pattern
            }],
            Priority=len(rules_response['Rules']) + 1,  # Set priority based on existing rules
            Actions=[{
                'Type': 'forward',
                'TargetGroupArn': target_group_arn
            }]
        )
        print(f"Path-based rule created for '{path_pattern}' on listener ARN: {listener_arn}")

    except Exception as e:
        print(f"Error creating path-based rule: {e}")

def wait_for_instances_running(ec2, instance_ids):
    """
    Wait for the specified EC2 instances to be in the running state.

    :param instance_ids: List of instance IDs to wait for.
    :type instance_ids: list[str]
    :raises ClientError: If there is an error from the AWS API.
    """
    print(f"Waiting for instances {instance_ids} to be running.")
    waiter = ec2.get_waiter('instance_running')
    try:
        waiter.wait(InstanceIds=instance_ids)
        print(f"Instances {instance_ids} are now running.")
    except ClientError as e:
        print(f"An error occurred while waiting for instances: {e}")
    except Exception as ex:
        print(f"An unexpected error occurred: {ex}")

async def call_endpoints_http(url, session, request_num, method):
    headers = {'content-type': 'application/json'}
    data = {}  # Ensure data is a valid JSON-serializable object
    try:
        if method.upper() == "POST":
            async with session.post(url, json=data, headers=headers) as response:
                status_code = response.status
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    response_json = await response.json()
                else:
                    response_json = await response.text()  # Fallback to text if not JSON
                print(f"Request {request_num} - Status Code: {status_code} - Response: {response_json}")
                return status_code, response_json
        else:
            async with session.get(url, headers=headers) as response:
                status_code = response.status
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    response_json = await response.json()
                else:
                    response_json = await response.text()  # Fallback to text if not JSON
                print(f"Request {request_num} - Status Code: {status_code} - Response: {response_json}")
                return status_code, response_json
    except Exception as e:
        print(f"Request {request_num}: Failed - {str(e)}")
        return None, str(e)

async def sendRequests(url, method, name):
        num_requests = 1000
        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            tasks = [call_endpoints_http(url, session, i, method) for i in range(num_requests)]
            await asyncio.gather(*tasks)
        end_time = time.time()
        print(f"\nTotal time taken : {end_time - start_time:.2f} seconds")
        print(f"Average time per request : {(end_time - start_time)/num_requests:.4f} seconds")
        print(f"This is the method used: {name}")

if __name__ == "__main__":
    # start by building the ressources
    tp3()
    print("-------> TP3 IaC script is done!")
