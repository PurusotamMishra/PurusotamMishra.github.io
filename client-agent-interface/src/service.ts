import axios from 'axios'
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

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

export const sendMessageToMcpClient = async (query: string) => {
  try {
    const response = await axios.post('http://localhost:8083/mcp/query', { query })
    const res = response.data
    const parts = res?.data?.data ?? []
    const data = JSON.parse(parts.join('\n'))
    return data
  } catch (error) {
    return {
      status: 'error',
      message: {
        error: "Failed to execute the query!",
        message: "Failed to execute the query!"
      }
    }
  }
}

export const sendMessageToA2AClient = async (query: string) => {
  try {
    const response = await axios.post('http://localhost:8083/test-client', { query })
    const res = response.data
    const parts = res.data.result?.parts ?? []
    const data = JSON.parse(parts.map((part: any) => part.text).join('\n'))
    return data
  } catch (error) {
    return {
      status: 'error',
      message: {
        error: "Failed to execute the query!",
        message: "Failed to execute the query!"
      }
    }
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