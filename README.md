AWS Deployment Tool
===================================
* * *

USAGE:
------------------------------
This tool intend to automate the deployment of 2 instances behind an ELB on AWS.  
There are 3 main commands:  
(main.py script located in client directory)   
`python main.py -c [start|stop|moveto]`
  
__START__   
Will start the deployment in the default region. (the REGION variable)
  
__stop__   
Will delete the deployment in the current region  

__MOVETO__  
Will send the current deployment a command to start a new deployment in the desired region.
After the deployment ends, The client will delete the deployment on the "old" region.


 


Prerequisites:
------------------------------  
1. **Set Your ENV Variables**:    
Execute the following commands in your shell:   
`echo AWS_ACCESS_KEY_ID=<YOUR KEY>`  
`echo AWS_SECRET_ACCESS_KEY==<YOUR  SECRET KEY>`
2. **Set Your ENV Variables on the AWS user-data script**  
Set the same keys in 'client/user-data.sh' file. it used to allow the EC2 instance use boto3 SDK.  
3. **Softwares And Packages**  
Ensure that Python3 is installed and run 'pip install -r requirements.txt' before using the tool.  

NOTE:
------------------------------   
The deployment will create the instances without SSH keys !  
You can add your SSH keys by doing the following:
1. in 'client/functions.py' file, set the KEY parameters.
2. in 'create_instance' section in the same file, add `KeyName=KEY_NAME`
 

