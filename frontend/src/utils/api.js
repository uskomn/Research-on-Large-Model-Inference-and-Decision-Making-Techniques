import axios from 'axios'

// 创建axios实例
const api = axios.create({
  baseURL: 'http://localhost:5000/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    console.error('API请求失败:', error)
    return Promise.reject(error)
  }
)

// 问答接口
export const chatApi = {
  sendMessage(message) {
    return api.post('/chat', { message })
  },
  healthCheck() {
    return api.get('/health')
  }
}

// 知识图谱接口
export const knowledgeApi = {
  getKnowledgeGraph() {
    return api.get('/knowledge-graph')
  },
  searchKnowledge(keyword) {
    return api.get('/knowledge/search', { params: { q: keyword } })
  }
}

export default api