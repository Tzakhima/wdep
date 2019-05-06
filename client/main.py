'''
v0.1

AWS Deployment Tool
----------------------
This tool is used to deploy instances behind an ELB on AWS.

Options:
start           - will deploy the instances in the default AWS region. instances will listen on a socket for commands.
stop            - Will remove the deployment.
moveto <region> - Will initiate a new deployment in the specified region and will destroy the existing.

'''

import click
import functions
import shelve

# Input parsing
@click.command()
@click.option('-c', '--command', type=click.Choice(['start', 'stop', 'moveto']), required=True, help='enter command to execute.')

# main function
def action(command):
    # Default region
    REGION = 'us-west-2'
    try:
        with shelve.open('regions', writeback=True) as db:
            REGION = db['default']
            print("Previous 'moveto' detected. Region: {}\n".format(REGION))
    except Exception:
        print("No previous 'moveto' detected. Region: {}\n".format(REGION))

    if command == "start":
        functions.start(REGION)
    elif command == "stop":
        functions.delete(REGION)
    elif command == "moveto":
        functions.moveto(REGION)




if __name__ == '__main__':
    print("-"*23)
    print("| AWS deployment tool |")
    print("-" * 23,"\n")
    action()