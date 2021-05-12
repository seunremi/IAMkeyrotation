import json
import boto3
sns_client=boto3.client('sns')
iam_client=boto3.client('iam')
from datetime import datetime
from datetime import timedelta




def lambda_handler(event, context):
    expired_list=scan_acces()
    
    TopicArn='arn:aws:sns:us-east-1:715804921220:s3put'
    Msg= 'Good Day Admin,below are the users with expired access key /n' + str(expired_list)
    access_sns(TopicArn, Msg)
    
    
expiration_list=[]
def scan_acces():
    response = iam_client.get_group(GroupName='developers')
    users=response['Users']
    for userinfo in users:
        username= userinfo['UserName']
        userid= userinfo['UserId']
        access_response = iam_client.list_access_keys(UserName=username)
        access_response=access_response['AccessKeyMetadata']
        for access_keys in access_response:
            ak=access_keys['AccessKeyId']
            cd=access_keys['CreateDate']
            c_date = cd.replace(tzinfo=None)
            diff= (datetime.now() - c_date).days
            days = 3
            if diff > days:
                del_access = iam_client.delete_access_key(UserName=username, AccessKeyId=ak)
                exp_dict={'uname':username,'Access_Key':ak, 'Creation_Date':c_date}
                expiration_list.append(exp_dict)
    return expiration_list
    
def access_sns(topic_arn, body_msg):
    response = sns_client.publish(TopicArn=topic_arn, Message=body_msg)
    return response
