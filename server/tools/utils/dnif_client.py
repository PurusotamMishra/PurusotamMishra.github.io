"""
DNIF API client functions for invoking, checking status, and retrieving query results (LangGraph version).
"""
import os
import requests
import asyncio

import sys
sys.path.append("/app/server")

import tools.utils.config as config_module

config = config_module.config


def _dnif_invoke_query_internal(query: str) -> dict:
    """
    Internal function to invoke a DQL query (not decorated with @function_tool).
    Used by external polling function.
    
    Args:
        query: The DQL query string to execute
        
    Returns:
        dict with 'success' boolean and either 'task_id' or 'error' message
    """
    if not config.validate():
        return {
            "success": False,
            "error": "Missing DNIF API credentials. Please configure DNIF_CONSOLE_DOMAIN, DNIF_CLUSTER_ID, and DNIF_API_TOKEN in your .env file."
        }
    
    url = f"https://{config.console_domain}/{config.cluster_id}/wrk/api/job/invoke"
    
    payload = {
        "query_timezone": config.timezone,
        "scope_id": config.scope_id,
        "job_type": "dql",
        "job_execution": "on-demand",
        "query": query
    }
    
    headers = {
        "Token": config.api_token,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=300, verify=True)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                task_id = data.get('data', [{}])[0].get('id')
                return {
                    "success": True,
                    "task_id": task_id,
                    "message": f"Query invoked successfully. Task ID: {task_id}"
                }
            else:
                return {
                    "success": False,
                    "error": f"Query invocation failed: {data.get('message', 'Unknown error')}"
                }
        else:
            return {
                "success": False,
                "error": f"HTTP Error {response.status_code}: {response.text}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Exception occurred: {str(e)}"
        }


def _dnif_check_status_internal(task_id: str) -> dict:
    """
    Internal function to check query status (not decorated with @function_tool).
    Used by external polling function.
    
    Args:
        task_id: The task ID returned from _dnif_invoke_query_internal
        
    Returns:
        dict with 'success' boolean, 'task_state', and 'task_stage'
    """
    if not config.validate():
        return {
            "success": False,
            "error": "Missing DNIF API credentials"
        }
    
    url = f"https://{config.console_domain}/{config.cluster_id}/wrk/api/dispatcher/task/state/{task_id}"
    
    headers = {
        "Token": config.api_token
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=300, verify=True)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                return {
                    "success": True,
                    "task_state": data.get('task_state'),
                    "task_stage": data.get('task_stage'),
                    "message": f"Task state: {data.get('task_state')}, Stage: {data.get('task_stage')}"
                }
            else:
                return {
                    "success": False,
                    "error": f"Status check failed: {data.get('message', 'Unknown error')}"
                }
        else:
            return {
                "success": False,
                "error": f"HTTP Error {response.status_code}: {response.text}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Exception occurred: {str(e)}"
        }


def _dnif_get_results_internal(task_id: str, pagesize: int = 100) -> dict:
    """
    Internal function to get query results (not decorated with @function_tool).
    Used by external polling function.
    
    Args:
        task_id: The task ID returned from _dnif_invoke_query_internal
        pagesize: Number of results to retrieve (default: 100)
        
    Returns:
        dict with 'success' boolean and 'results' list or 'error' message
    """
    if not config.validate():
        return {
            "success": False,
            "error": "Missing DNIF API credentials"
        }
    
    url = f"https://{config.console_domain}/{config.cluster_id}/wrk/api/dispatcher/task/result/{task_id}?pagesize={pagesize}&pageno=1"
    
    headers = {
        "Token": config.api_token
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30, verify=True)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('status') == 'success':
                # According to DNIF API docs, results are in 'result' field (singular)
                # Also check for other possible field names as fallback
                results = None
                total_count = data.get('total_count', 0)
                
                if 'result' in data:
                    results = data.get('result', [])
                elif 'documents' in data:
                    results = data.get('documents', [])
                elif 'data' in data:
                    # 'data' might contain task info, not results
                    data_field = data.get('data', [])
                    # Check if data is actually a list of results
                    if isinstance(data_field, list) and data_field and isinstance(data_field[0], dict) and 'id' not in data_field[0]:
                        results = data_field
                    else:
                        results = []
                else:
                    results = []
                
                # Ensure results is a list
                if not isinstance(results, list):
                    results = []
                
                return {
                    "success": True,
                    "results": results,
                    "count": len(results),
                    "total_count": total_count,
                    "message": f"Retrieved {len(results)} records (total available: {total_count})"
                }
            else:
                return {
                    "success": False,
                    "error": f"Results fetch failed: {data.get('message', 'Unknown error')}"
                }
        else:
            return {
                "success": False,
                "error": f"HTTP Error {response.status_code}: {response.text}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Exception occurred: {str(e)}"
        }


async def execute_query_with_external_polling(
    query: str,
    poll_interval: int = None,
    max_wait_time: int = None
) -> dict:
    """
    Execute a DQL query with external polling to avoid max turns limit.
    
    Args:
        query: The DQL query string to execute
        poll_interval: Seconds between status checks (default: from config)
        max_wait_time: Maximum total wait time in seconds (default: from config)
        
    Returns:
        dict with 'success' boolean, 'results' list, 'count', and 'error' if failed
    """
    poll_interval = poll_interval or config.poll_interval
    max_wait_time = max_wait_time or config.max_wait_time
    
    # Step 1: Invoke query
    invoke_result = _dnif_invoke_query_internal(query)
    if not invoke_result.get('success'):
        return {
            "success": False,
            "error": invoke_result.get('error', 'Failed to invoke query'),
            "results": [],
            "count": 0
        }
    
    task_id = invoke_result.get('task_id')
    if not task_id:
        return {
            "success": False,
            "error": "No task_id returned from query invocation",
            "results": [],
            "count": 0
        }
    
    print(f"[DEBUG] Query invoked with task_id: {task_id}")
    
    # Step 2: Poll status with external polling
    max_checks = max_wait_time // poll_interval
    check_count = 0
    
    while check_count < max_checks:
        check_count += 1
        status_result = _dnif_check_status_internal(task_id)
        
        if not status_result.get('success'):
            return {
                "success": False,
                "error": f"Status check failed: {status_result.get('error', 'Unknown error')}",
                "results": [],
                "count": 0,
                "task_id": task_id
            }
        
        task_state = status_result.get('task_state')
        task_stage = status_result.get('task_stage', '')
        
        print(f"[DEBUG] Poll {check_count}/{max_checks}: task_state={task_state}, task_stage={task_stage}")
        
        # Check for completion
        if task_state == 'SUCCESS':
            print(f"[DEBUG] Query completed successfully after {check_count} checks")
            # Step 3: Get results
            results_result = _dnif_get_results_internal(task_id)
            if results_result.get('success'):
                return {
                    "success": True,
                    "results": results_result.get('results', []),
                    "count": results_result.get('count', 0),
                    "total_count": results_result.get('total_count', 0),
                    "task_id": task_id,
                    "checks_performed": check_count
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to retrieve results: {results_result.get('error', 'Unknown error')}",
                    "results": [],
                    "count": 0,
                    "task_id": task_id
                }
        
        # Check for failure states
        elif task_state in ['FAILED', 'QUERY_WORKERS_DOWN']:
            return {
                "success": False,
                "error": f"Query execution failed: task_state={task_state}, task_stage={task_stage}",
                "results": [],
                "count": 0,
                "task_id": task_id
            }
        
        # Query still processing - wait before next check
        if check_count < max_checks:
            await asyncio.sleep(poll_interval)
    
    # Timeout after max_wait_time
    return {
        "success": False,
        "error": f"Query execution timeout after {max_wait_time} seconds ({max_checks} checks). Task ID: {task_id}. Query may still be processing.",
        "results": [],
        "count": 0,
        "task_id": task_id,
        "checks_performed": check_count
    }

