# How to run TP3
Instructions are provided for debian distros. Adapt to your distro if needed

## Prerequesites
Have the following installed on your local machine : 
```
apt-get update
apt install git -y
apt install python3 -y
apt install python3-pip -y
apt install python3-boto3 -y
apt install python3-dotenv -y
apt install python3-paramiko -y
apt install python3-requests -y
apt install python3-aiohttp -y
```

## Prepare environment
- Connect to awsacademylab and start your lab module.
- Copy the template.env file as .env
```
cp template.env .env
```
- Copy the aws details credentials inside the .env file
- Run the script
```
./script.sh
```

## Options
The tp3.py python script here are the options that can be set by the user.
1. ``build_image`` : if set to true, this will build a golden image that are used by the worker instances. It is required on the first run, but once we have our AMI, it can be set to false to make the script skip this part.
