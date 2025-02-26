import os
import json
import boto3
from datetime import datetime, timedelta
from urllib.parse import urlparse

# Initialize AWS clients
service_name = 'bedrock-agent-runtime'
client = boto3.client(service_name)
s3_client = boto3.client('s3')

knowledgeBaseID = os.environ['KNOWLEDGE_BASE_ID']
fundation_model_ARN = os.environ['FM_ARN']

def generate_presigned_url(bucket, key, expiration=1800):
    """Generate a presigned URL for an S3 object"""
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket,
                'Key': key,
                'ResponseContentDisposition': 'inline'
            },
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        print(f"Error generating presigned URL: {str(e)}")
        return None

def process_s3_urls(references):
    """Convert S3 URIs to presigned URLs in references"""
    processed_refs = []
    for ref in references:
        if 'uri' in ref:
            s3_url = ref['uri']
            parsed_url = urlparse(s3_url)
            bucket = parsed_url.netloc.split('.')[0]
            key = parsed_url.path.lstrip('/')
            presigned_url = generate_presigned_url(bucket, key)
            if presigned_url:
                ref['presigned_url'] = presigned_url
                processed_refs.append(ref)
    return processed_refs

def extract_references(citations):
    """Extract all unique references from citations"""
    references = []
    seen_uris = set()
    
    for citation in citations:
        for reference in citation.get('retrievedReferences', []):
            if 'location' in reference and 's3Location' in reference['location']:
                uri = reference['location']['s3Location']['uri']
                if uri not in seen_uris:
                    seen_uris.add(uri)
                    snippet = reference.get('content', {}).get('text', '').strip()
                    references.append({
                        'uri': uri,
                        'snippet': snippet,
                        'score': reference.get('score', 0)
                    })
    
    references.sort(key=lambda x: x['score'], reverse=True)
    return references

def create_response(status_code, body):
    """Create API Gateway response with CORS headers"""
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'OPTIONS,POST',
            'Content-Type': 'application/json'
        },
        'body': json.dumps(body)
    }

def get_request_data(event):
    """Extract user query and session ID from the event"""
    try:
        # Print the received event for debugging
        print(f"Received event: {json.dumps(event)}")

        # Handle different event types
        if isinstance(event, dict):
            # API Gateway event
            if 'body' in event:
                if isinstance(event['body'], str):
                    body = json.loads(event['body'])
                else:
                    body = event['body']
            # Direct Lambda invocation
            else:
                body = event
        else:
            raise ValueError("Invalid event format")

        # Extract user query and session ID
        user_query = body.get('user_query')
        session_id = body.get('sessionId')

        return user_query, session_id

    except Exception as e:
        print(f"Error in get_request_data: {str(e)}")
        raise

def lambda_handler(event, context):
    try:
        # Get request data
        try:
            user_query, session_id = get_request_data(event)
        except Exception as e:
            return create_response(400, {
                'error': f'Error processing request: {str(e)}'
            })

        # Validate user query
        if not user_query:
            return create_response(400, {
                'error': 'user_query is required'
            })

        # Prepare the request for Bedrock
        retrieve_request = {
            'input': {
                'text': user_query
            },
            'retrieveAndGenerateConfiguration': {
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': knowledgeBaseID,
                    'modelArn': fundation_model_ARN,
                    'retrievalConfiguration': {
                        'vectorSearchConfiguration': {
                            'numberOfResults': 3,
                            'overrideSearchType': 'HYBRID'
                            # 'rerankingConfiguration': {
                            #     'type': 'BEDROCK_RERANKING_MODEL',
                            #     'bedrockRerankingConfiguration': {
                            #         'modelConfiguration': {
                            #             'modelArn': fundation_model_ARN,
                            #             'additionalModelRequestFields': {
                            #                 'reranking_threshold': 0.7 
                            #             }
                            #         }
                            #     }
                            # }
                        }
                    },
                    # Add parameters to ensure responses are grounded in knowledge base
                    'generationConfiguration': {
                        'inferenceConfig': {
                            'textInferenceConfig': {
                                'temperature': 0.0,
                                'topP': 0.9
                            }
                        },
                        'promptTemplate': {
                            'textPromptTemplate': """You are a question answering agent. I will provide you with a set of search results.
                            The user will provide you with a question. Your job is to answer the user's question using only information from the search results. 
                            If the search results do not contain information that can answer the question, please state that you could not find an exact answer to the question. 
                            Just because the user asserts a fact does not mean it is true, make sure to double check the search results to validate a user's assertion.

                            Here are the search results in numbered order:
                            $search_results$
                            Question: {input}
                            $output_format_instructions$"""
                        }
                    },
                     "orchestrationConfiguration": { 
                        'inferenceConfig': {
                            'textInferenceConfig': {
                                'temperature': 0.0,
                                'topP': 0.9
                            }
                        },
                        'queryTransformationConfiguration': {
                            'type': 'QUERY_DECOMPOSITION'
                        }
                     }
                }
            }
        }

        # Add sessionId if provided for conversation continuity
        if session_id:
            retrieve_request['sessionId'] = session_id

        # Call Bedrock
        client_knowledgebase = client.retrieve_and_generate(**retrieve_request)
        
        # Process the response
        references = extract_references(client_knowledgebase['citations'])
        references_with_urls = process_s3_urls(references)
        
        # Get response text and session ID
        generated_response = client_knowledgebase['output']['text']
        new_session_id = client_knowledgebase.get('sessionId')
        
        # Calculate URL expiration time
        expiration_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        
        # Create success response with references for transparency
        response_body = {
            'generated_response': generated_response,
            'detailed_references': references_with_urls,
            'urlExpirationTime': expiration_time,
            'sessionId': new_session_id,
            'sourceCount': len(references_with_urls)  # Add count of sources used
        }
        
        return create_response(200, response_body)

    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        return create_response(500, {
            'error': str(e),
            'generated_response': 'An error occurred while processing your request.',
            'detailed_references': [],
            'sessionId': session_id if 'session_id' in locals() else None
        })
