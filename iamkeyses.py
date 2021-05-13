from collections import defaultdict
from datetime import datetime, timezone
import logging

import boto3
from botocore.exceptions import ClientError


# How many days before sending alerts about the key age?
ALERT_AFTER_N_DAYS = 90 # TODO: confirm wether we want alerts to come in 5 days prior or 14 days; discrepency between verbal and ticket requests! 
# When To delete
DELETE_AFTER = 91
# How ofter we have set the cron to run the Lambda?
SEND_EVERY_N_DAYS = 1
# Who send the email?
SES_SENDER_EMAIL_ADDRESS = 'example@example.com' # TODO: confirm email.
# Where did we setup SES?
SES_REGION_NAME = 'us-east-1' 

iam_client = boto3.client('iam')
ses_client = boto3.client('ses', region_name=SES_REGION_NAME)

# Helper function to choose if a key owner should be notified today
def is_key_interesting(key):
    str = 'not_interesting'
    # If the key is inactive, it is not interesting
    if key['Status'] != 'Active':
        return False

    elapsed_days = (datetime.now(timezone.utc) - key['CreateDate']).days
    
    # If the key is newer than ALERT_AFTER_N_DAYS, we don't need to notify the
    # owner
    if elapsed_days < ALERT_AFTER_N_DAYS:
        return False

    return True

# Helper to send the notification to the user. We need the receiver email, 
# the keys we want to notify the user about, and on which account we are
# TODO: Modify to indicate last day before deletion.
def send_notification(email, keys, account_id, action):
    if (account_id == ''):
        profile_name='cars_np'
    elif (account_id == ''):
        profile_name='cars_prod'
    else:
        logging.info(f'Account ID: {account_id} not in cars_np or cars_prod')
    # TODO: update email message to reflect the profile name and maths according to alerting schedule, and relevant in-house documentation
    if (action == 'warn'): #TODO finish this!
        #warning email body
        email_text = f'''Dear {keys[0]['UserName']},
this is an automatic reminder to rotate your AWS Access Keys at least every {ALERT_AFTER_N_DAYS} days.

At the moment, you have {len(keys)} key(s) on the account {account_id} that have been created more than {ALERT_AFTER_N_DAYS} days ago:
'''
    for key in keys:
        email_text += f"- {key['AccessKeyId']} was created on {key['CreateDate']} ({(datetime.now(timezone.utc) - key['CreateDate']).days} days ago)\n"
    
    email_text += f"""
To learn how to rotate your AWS Access Key, please read the official guide at https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html#Using_RotateAccessKey
If you have any question, please don't hesitate to contact the Support Team at support@example.com.

This automatic reminder will be sent again in {SEND_EVERY_N_DAYS} day(s), if the key(s) will not be rotated.

Regards,
Your lovely Support Team
"""

    elif (action == 'delete'):
        #TODO fill in the email for deletion alert as above
        email_text = f''' WARNING EMAIL
'''

    
    try:
        ses_response = ses_client.send_email(
            Destination={'ToAddresses': [email]},
            Message={
                'Body': {'Html': {'Charset': 'UTF-8', 'Data': email_text}},
                'Subject': {'Charset': 'UTF-8',
                            'Data': f'Remember to rotate your AWS Keys on account {account_id}!'}
            },
            Source=SES_SENDER_EMAIL_ADDRESS
        )
    except ClientError as e:
        logging.error(e.response['Error']['Message'])
    else:
        logging.info(f'Notification email sent successfully to {email}! Message ID: {ses_response["MessageId"]}')

def lambda_handler(event, context):
    users = []
    is_truncated = True
    marker = None
    
    # We retrieve all users associated to the AWS Account.  
    # Results are paginated, so we go on until we have them all
    while is_truncated:
        # This strange syntax is here because `list_users` doesn't accept an 
        # invalid Marker argument, so we specify it only if it is not None
        response = iam_client.list_users(**{k: v for k, v in (dict(Marker=marker)).items() if v is not None})
        users.extend(response['Users'])
        is_truncated = response['IsTruncated']
        marker = response.get('Marker', None)
    
    # Probably in this list you have bots, or users you want to filter out
    # You can filter them by associated tags, or as I do here, just filter out 
    # all the accounts that haven't logged in the web console at least once
    # (probably they aren't users)
    filtered_users = list(filter(lambda u: u.get('PasswordLastUsed'), users))
    
    interesting_keys = []

    # For every user, we want to retrieve the related access keys
    # TODO: To filter by users in a group; eventually we'll have every user in viewers 
    for user in filtered_users:
        response = iam_client.list_access_keys(UserName=user['UserName'])
        access_keys = response['AccessKeyMetadata']
        
        # We are interested only in Active keys, older than
        # ALERT_AFTER_N_DAYS days
        interesting_keys.extend(list(filter(lambda k: is_key_interesting(k), access_keys)))
    
    # We group the keys by owner, so we send no more than one notification for every user
    # interesting_keys_grouped_by_user = defaultdict(list)
    delete_keys_grouped_by_user = defaultdict(list)
    warning_keys_grouped_by_user = defaultdict(list)
    for key in interesting_keys:
        elapsed_days = (datetime.now(timezone.utc) - key['CreateDate']).days
    
        # If the key is newer than ALERT_AFTER_N_DAYS, we don't need to notify the
        # owner
        if elapsed_days >= DELETE_AFTER:
            delete_keys_grouped_by_user[key['UserName']].append(key)
        else:
            warning_keys_grouped_by_user[key['UserName']].append(key)
    
    # In our AWS account the username is always a valid email. 
    # We also get the account id from the Lambda context, but you can 
    # also specify any id you want here, it's only used in the email 
    # sent to the users to let them know on which account they should
    # check
    for user in warning_keys_grouped_by_user.values():
        action='warn'
        send_notification(user[0]['UserName'], user, context.invoked_function_arn.split(":")[4], action)

    for user in delete_keys_grouped_by_user.values():
        action='delete'
        send_notification(user[0]['UserName'], user, context.invoked_function_arn.split(":")[4], action)        
    for user in delete_keys_grouped_by_user.values():
        action='delete'
        send_notification(user[0]['UserName'], user, context.invoked_function_arn.split(":")[4], action)   
        response = iam_client.delete_access_key(
            UserName=user[0]['UserName'],
            AccessKeyId='user'
        )   

