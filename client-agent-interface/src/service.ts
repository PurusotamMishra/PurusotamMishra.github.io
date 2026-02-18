import axios from 'axios'
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

export const sendMessageToClient = async (query: string, type: 'a2a' | 'mcp') => {
  const response = await axios.post('http://localhost:8083/send-message', { query, type })
  return response.data
}


export type DataResponse = {
  type: string;
  data?: {
    error: null | string;
    is_enrichment: boolean;
    key_answer: string;
    one_line_summary: string;
    original_query: null | string
    query: string
    query_idx: number
    result_count: number
    results: Record<string, any>[]
    source: string
  }
}

export const apiQuery = async (query: string) => {
  await sleep(1000);
  const response = await axios.post('http://localhost:8082/api/query', { query })
  try {
    const data: DataResponse = JSON.parse(response.data?.data?.[0] || '{}')
    return data
  } catch (error) {
    return {
      status: 'error',
      message: {
        error: response.data.error,
        message: response.data.message
      }
    }
  }
}