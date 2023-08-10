
import streamlit as st
# Hide default Streamlit footer
hide_streamlit_style = """
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
    </style>
"""
#give it a ash background
st.markdown("""
    <style>
        .reportview-container {
            background: #B2BEB5;  # Ash color
        }
        .main .block-container {
            background: #B2BEB5;  # Ash color
        }
    </style>
    """,
    unsafe_allow_html=True,
)




st.markdown(hide_streamlit_style, unsafe_allow_html=True)
import base64
from langchain.llms.bedrock import Bedrock
import boto3
from langchain.retrievers import AmazonKendraRetriever
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
import json
from botocore.exceptions import ClientError
import requests
import base64
from requests.exceptions import HTTPError

if 'custom_details' not in st.session_state:
    st.session_state.custom_details = False
    st.session_state.username = ""
    st.session_state.confluence_url = ""
    st.session_state.confluence_api_token = ""
    st.session_state.space_key = ""
    st.session_state.content = "" # Add this line to save the generated content


# function for encoding image to base64
def get_image_base64(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()
    
def get_secret():
    secret_name = "kendraRagApp"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager', region_name='ap-south-1'
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        raise e

    # Decrypts secret using the associated KMS key.
    secret = get_secret_value_response['SecretString']
    return secret   

# Generating and Publishing new articles to Atlassian Confluence Space
def publish(content, use_custom_details=False, username=None, confluence_url=None, confluence_api_token=None, space_key=None):

    # If not using custom details, get the default details
    if not use_custom_details:
        secrets = json.loads(get_secret())
        username = secrets['username']
        confluence_url = secrets['confluence_space_url']
        confluence_api_token = secrets['confluence_token']
        space_key = secrets['space_key']

    parent_page_id = None #we are publishing to the main content view
    content = content.lstrip("\n")
    title_end_index = content.find("\n")
    new_page_title = content[:title_end_index].strip()
    new_page_content = content[title_end_index:].strip()
    
    auth_str = f"{username}:{confluence_api_token}"

    # Set the API endpoint URL
    url = f"{confluence_url}"
    auth_str_encoded = base64.b64encode(auth_str.encode()).decode()
    # Set the request headers, including the API token or credentials for authentication
    headers = {
        "Authorization": f"Basic {auth_str_encoded}",
        "Content-Type": "application/json"
    }

    # Set the request payload with the new page information
    data = {
        "type": "page",
        "title": new_page_title,
        "space": {"key": space_key},
        "body": {
            "storage": {
                "value": new_page_content,
                "representation": "storage",
            }
        }
    }
    # If the new page should be a child page, specify the parent page ID
    if parent_page_id:
       data["ancestors"]=[{"type": "page", "id": parent_page_id}]


    try:
        # send post request to create the new page
        response = requests.post(url, headers=headers, json=data)
        # If the response was successful, no Exception will be raised
        response.raise_for_status()
    except HTTPError as http_err:
        # If status code is 400, it might be due to duplicate page title
        if response.status_code == 400:
            st.write(f'HTTP error occurred: {http_err}. A page might already exist with the same title.\n Select another query or type in a new query')
        else:
            st.write(f'HTTP error occurred: {http_err}.')
    except Exception as err:
        st.write(f'Other error occurred: {err}.')
    else:
        st.write('Page successfully created.')

def qa(query, temperature, topP):
    secrets = json.loads(get_secret())
    kendra_index_id = secrets['kendra_index_id']
    aws_access_key_id = secrets['aws_access_key_id']
    aws_secret_access_key = secrets['aws_secret_access_key']
    BEDROCK_CLIENT = boto3.client('bedrock', region_name='us-east-1', aws_access_key_id=aws_access_key_id,aws_secret_access_key=aws_secret_access_key)
    llm = Bedrock(model_id="amazon.titan-tg1-large", region_name='us-east-1', model_kwargs={"maxTokenCount": 4096, "temperature": temperature, "topP": topP}, client = BEDROCK_CLIENT)
    #top-p is the probability of the most likely token to be sampled, meaning that the model will sample from the most likely tokens with a probability of 0.9, hence the model will be more conservative in its sampling. The range of top-p is between 0 and 1.
    #temperature is a scaling factor for the logits distribution. The range of temperature is between 0 and 1. The lower the temperature, the more conservative the model will be in its sampling. Different temperature values can be used to trade off quality and diversity.
    KENDRA_CLIENT = boto3.client('kendra', region_name='ap-south-1', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)
    

    retriever = AmazonKendraRetriever(index_id=kendra_index_id, region_name='ap-south-1', client=KENDRA_CLIENT)
    
    prompt_template = """
    {context}
    {question} If you are unable to find the relevant article, respond 'Sorry! I can't generate the needed content based on the context provided.'
    """
    
    PROMPT = PromptTemplate(
    template=prompt_template, input_variables=["context", "question"])
    
    chain = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=retriever,
    verbose=True,
    chain_type_kwargs={
    "prompt": PROMPT
    }
    )
    
    return chain(query)

# Developing a Streamlit App interface


#st.image("https://karaamanalytics.com/wp-content/uploads/2022/12/karaamA-1.svg")
#st.image("https://www.capgemini.com/wp-content/themes/capgemini-komposite/assets/images/logo.svg")

st.title("Retrieval Augmented Generation with Kendra, Amazon Bedrock, and LangChain")
#creating a sidebar with a title and sliders for temperature and top-p
with st.sidebar:
    st.title("Inference Parameters")
    temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.5, step=0.1)
    topP = st.slider("Top-p", min_value=0.0, max_value=1.0, value=0.5, step=0.1)

#creating a text input box for the query
input = st.text_input('Enter your query: ')

if st.button('Generate'):
    #add a spinner
    with st.spinner('Generating content...'):
        response = qa(input, temperature, topP)
        if response.get("result"):
            st.session_state.content = response["result"]

# Outside the 'Generate' button block
if 'content' in st.session_state:
    st.subheader('Generated Content')
    st.write(st.session_state.content)
    publish_to_confluence = st.radio("Do you want to publish the content to Confluence?", ("No", "Yes"))
    st.session_state.publish_to_confluence = publish_to_confluence

    if publish_to_confluence == "Yes":
        # show the sidebar with the confluence details
        st.sidebar.header("Confluence Space")
        st.session_state.custom_details = st.sidebar.checkbox("Use custom details", st.session_state.custom_details) #session_state.custom_details is a boolean value that is True if the user has selected to use custom details
        if st.session_state.custom_details:
            st.session_state.username = st.sidebar.text_input("Please enter your confluence email:", st.session_state.username)
            st.session_state.confluence_url = st.sidebar.text_input("Please enter your Confluence space url:", st.session_state.confluence_url)
            st.session_state.confluence_api_token = st.sidebar.text_input("Please enter your Confluence API token:", st.session_state.confluence_api_token)
            st.session_state.space_key = st.sidebar.text_input("Please enter your Confluence space key:", st.session_state.space_key)
            #check if the user has entered all the details then enable the publish button
            if st.session_state.username and st.session_state.confluence_url and st.session_state.confluence_api_token and st.session_state.space_key:
                if st.button("Publish"):
                    publish(st.session_state.content, use_custom_details=True, username=st.session_state.username, confluence_url=st.session_state.confluence_url, confluence_api_token=st.session_state.confluence_api_token, space_key=st.session_state.space_key)
        else:
            st.session_state.username = None
            st.session_state.confluence_url = None
            st.session_state.confluence_api_token = None
            st.session_state.space_key = None
            if st.button("Publish"):
                publish(st.session_state.content)
    else:
        # if user selects 'No' do nothing
        pass

else:
    st.subheader('Sorry!')
    st.write("Could not answer the query based on the context available")


aws_kendra_logo = get_image_base64("kendra.jpg")
langchain_logo = get_image_base64("langchain.png")
bedrock_logo = get_image_base64("bedrock.png")
ec2_logo = get_image_base64("Amazon_ec2.png")
secrets_manager_logo = get_image_base64("AWS_secrets.png")
s3_logo = get_image_base64("s3-bucket.png")

st.markdown(f"""
    <div style="text-align: left;">
        <small>Powered by</small>
        <img src="data:image/jpg;base64,{bedrock_logo}" alt="Amazon Bedrock" style="height: 40px; padding-left: 5px;">
        <img src="data:image/jpg;base64,{aws_kendra_logo}" alt="AWS Kendra" style="height: 40px; padding-left: 5px;">
        <img src="data:image/jpg;base64,{langchain_logo}" alt="Langchain" style="height: 40px; padding-left: 5px;">
        <img src="data:image/jpg;base64,{ec2_logo}" alt="EC2" style="height: 40px; padding-left: 5px;">
        <img src="data:image/jpg;base64,{secrets_manager_logo}" alt="Secrets Manager" style="height: 40px; padding-left: 5px;">
        <img src="data:image/jpg;base64,{s3_logo}" alt="S3" style="height: 40px; padding-left: 5px;">
    </div>
""", unsafe_allow_html=True)
