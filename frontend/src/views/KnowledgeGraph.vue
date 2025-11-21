<template>
  <div class="knowledge-graph-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h3>
        <el-icon><Connection /></el-icon>
        医疗知识图谱
      </h3>
      <p class="subtitle">可视化展示重症伤员处置相关的知识关联</p>
    </div>

    <!-- 控制面板 -->
    <div class="control-panel">
      <el-row :gutter="16" align="middle">
        <el-col :span="8">
          <el-button @click="resetView" type="primary" plain>
            <el-icon><Refresh /></el-icon>
            重置视图
          </el-button>
          <el-button @click="toggleLabels">
            <el-icon><View /></el-icon>
            {{ showLabels ? '隐藏标签' : '显示标签' }}
          </el-button>
        </el-col>
        <el-col :span="8">
          <el-select v-model="selectedNodeType" placeholder="筛选节点类型" clearable>
            <el-option label="全部" value="" />
            <el-option label="系统" value="system" />
            <el-option label="疾病" value="disease" />
            <el-option label="症状" value="symptom" />
            <el-option label="处置" value="treatment" />
            <el-option label="原因" value="cause" />
          </el-select>
        </el-col>
        <el-col :span="8">
          <div class="graph-info">
            <el-tag type="info" size="small">
              节点: {{ filteredNodes.length }} | 连接: {{ filteredLinks.length }}
            </el-tag>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 图谱容器 -->
    <div class="graph-container" ref="graphContainer">
      <div v-if="isLoading" class="loading">
        <el-icon class="loading-icon"><Loading /></el-icon>
        <span>正在加载知识图谱...</span>
      </div>
      <svg v-show="!isLoading" ref="svg" :width="svgWidth" :height="svgHeight"></svg>
    </div>

    <!-- 节点详情面板 -->
    <el-drawer
      v-model="showDetails"
      title="节点详情"
      direction="rtl"
      size="30%"
    >
      <div v-if="selectedNode">
        <h4>{{ selectedNode.label }}</h4>
        <el-tag :type="getNodeTypeColor(selectedNode.group)" size="small">
          {{ getNodeTypeText(selectedNode.group) }}
        </el-tag>
        
        <div class="node-connections">
          <h5>相关连接:</h5>
          <ul>
            <li v-for="link in getNodeConnections(selectedNode.id)" :key="link.target || link.source">
              {{ getNodeName(link.target || link.source) }}
            </li>
          </ul>
        </div>
      </div>
    </el-drawer>

    <!-- 图例 -->
    <div class="legend">
      <h5>图例</h5>
      <div class="legend-items">
        <div class="legend-item" v-for="(color, type) in nodeColors" :key="type">
          <div class="legend-color" :style="{ backgroundColor: color }"></div>
          <span>{{ getNodeTypeText(type) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, nextTick, computed, watch } from 'vue'
import { knowledgeApi } from '../utils/api'
import { ElMessage } from 'element-plus'
import * as d3 from 'd3'

export default {
  name: 'KnowledgeGraph',
  setup() {
    const graphContainer = ref(null)
    const svg = ref(null)
    const isLoading = ref(true)
    const showLabels = ref(true)
    const showDetails = ref(false)
    const selectedNode = ref(null)
    const selectedNodeType = ref('')
    
    const svgWidth = ref(800)
    const svgHeight = ref(600)
    
    const graphData = ref({ nodes: [], links: [] })
    
    // 节点颜色映射
    const nodeColors = {
      root: '#ff6b6b',
      system: '#4ecdc4',
      disease: '#45b7d1',
      symptom: '#96ceb4',
      treatment: '#ffeaa7',
      cause: '#dda0dd'
    }

    // 计算过滤后的节点和连接
    const filteredNodes = computed(() => {
      if (!selectedNodeType.value) return graphData.value.nodes
      return graphData.value.nodes.filter(node => node.group === selectedNodeType.value)
    })

    const filteredLinks = computed(() => {
      const nodeIds = new Set(filteredNodes.value.map(node => node.id))
      return graphData.value.links.filter(link => 
        nodeIds.has(link.source) && nodeIds.has(link.target)
      )
    })

    // 初始化图谱
    const initGraph = async () => {
      try {
        isLoading.value = true
        const response = await knowledgeApi.getKnowledgeGraph()
        graphData.value = response
        
        await nextTick()
        renderGraph()
      } catch (error) {
        console.error('加载知识图谱失败:', error)
        ElMessage.error('加载知识图谱失败')
      } finally {
        isLoading.value = false
      }
    }

    // 渲染图谱
    const renderGraph = () => {
      if (!svg.value || !graphContainer.value) return

      // 获取容器尺寸
      const containerRect = graphContainer.value.getBoundingClientRect()
      svgWidth.value = containerRect.width - 20
      svgHeight.value = containerRect.height - 140

      // 清空之前的内容
      d3.select(svg.value).selectAll('*').remove()

      const svgElement = d3.select(svg.value)
      const g = svgElement.append('g')

      // 设置缩放行为
      const zoom = d3.zoom()
        .scaleExtent([0.1, 4])
        .on('zoom', (event) => {
          g.attr('transform', event.transform)
        })

      svgElement.call(zoom)

      // 创建力导向图
      const simulation = d3.forceSimulation(filteredNodes.value)
        .force('link', d3.forceLink(filteredLinks.value).id(d => d.id).distance(100))
        .force('charge', d3.forceManyBody().strength(-300))
        .force('center', d3.forceCenter(svgWidth.value / 2, svgHeight.value / 2))
        .force('collision', d3.forceCollide().radius(30))

      // 绘制连接线
      const links = g.append('g')
        .selectAll('line')
        .data(filteredLinks.value)
        .enter().append('line')
        .attr('stroke', '#999')
        .attr('stroke-opacity', 0.6)
        .attr('stroke-width', d => Math.sqrt(d.value))

      // 绘制节点
      const nodes = g.append('g')
        .selectAll('circle')
        .data(filteredNodes.value)
        .enter().append('circle')
        .attr('r', 15)
        .attr('fill', d => nodeColors[d.group] || '#999')
        .attr('stroke', '#fff')
        .attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .on('click', (event, d) => {
          selectedNode.value = d
          showDetails.value = true
        })
        .on('mouseover', function(event, d) {
          d3.select(this).attr('r', 18)
        })
        .on('mouseout', function(event, d) {
          d3.select(this).attr('r', 15)
        })
        .call(d3.drag()
          .on('start', dragstarted)
          .on('drag', dragged)
          .on('end', dragended)
        )

      // 添加标签
      const labels = g.append('g')
        .selectAll('text')
        .data(filteredNodes.value)
        .enter().append('text')
        .text(d => d.label)
        .attr('font-size', 12)
        .attr('dx', 20)
        .attr('dy', 4)
        .attr('fill', '#333')
        .style('pointer-events', 'none')
        .style('display', showLabels.value ? 'block' : 'none')

      // 更新位置
      simulation.on('tick', () => {
        links
          .attr('x1', d => d.source.x)
          .attr('y1', d => d.source.y)
          .attr('x2', d => d.target.x)
          .attr('y2', d => d.target.y)

        nodes
          .attr('cx', d => d.x)
          .attr('cy', d => d.y)

        labels
          .attr('x', d => d.x)
          .attr('y', d => d.y)
      })

      // 拖拽函数
      function dragstarted(event, d) {
        if (!event.active) simulation.alphaTarget(0.3).restart()
        d.fx = d.x
        d.fy = d.y
      }

      function dragged(event, d) {
        d.fx = event.x
        d.fy = event.y
      }

      function dragended(event, d) {
        if (!event.active) simulation.alphaTarget(0)
        d.fx = null
        d.fy = null
      }
    }

    // 重置视图
    const resetView = () => {
      const svgElement = d3.select(svg.value)
      svgElement.transition().duration(750).call(
        d3.zoom().transform,
        d3.zoomIdentity
      )
    }

    // 切换标签显示
    const toggleLabels = () => {
      showLabels.value = !showLabels.value
      const labels = d3.select(svg.value).selectAll('text')
      labels.style('display', showLabels.value ? 'block' : 'none')
    }

    // 获取节点类型颜色
    const getNodeTypeColor = (type) => {
      const colorMap = {
        root: 'danger',
        system: 'success',
        disease: 'primary',
        symptom: 'warning',
        treatment: 'info',
        cause: ''
      }
      return colorMap[type] || 'info'
    }

    // 获取节点类型文本
    const getNodeTypeText = (type) => {
      const textMap = {
        root: '根节点',
        system: '系统',
        disease: '疾病',
        symptom: '症状',
        treatment: '处置',
        cause: '原因'
      }
      return textMap[type] || type
    }

    // 获取节点连接
    const getNodeConnections = (nodeId) => {
      return graphData.value.links.filter(link => 
        link.source === nodeId || link.target === nodeId ||
        link.source.id === nodeId || link.target.id === nodeId
      )
    }

    // 获取节点名称
    const getNodeName = (nodeId) => {
      const node = graphData.value.nodes.find(n => n.id === nodeId)
      return node ? node.label : nodeId
    }

    // 监听节点类型筛选变化
    watch(selectedNodeType, () => {
      renderGraph()
    })

    onMounted(() => {
      initGraph()
      window.addEventListener('resize', () => {
        renderGraph()
      })
    })

    return {
      graphContainer,
      svg,
      isLoading,
      showLabels,
      showDetails,
      selectedNode,
      selectedNodeType,
      svgWidth,
      svgHeight,
      nodeColors,
      filteredNodes,
      filteredLinks,
      resetView,
      toggleLabels,
      getNodeTypeColor,
      getNodeTypeText,
      getNodeConnections,
      getNodeName
    }
  }
}
</script>

<style scoped>
.knowledge-graph-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f5f7fa;
}

.page-header {
  background: white;
  padding: 20px;
  border-bottom: 1px solid #e4e7ed;
}

.page-header h3 {
  margin: 0;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 8px;
}

.subtitle {
  margin: 5px 0 0 0;
  color: #909399;
  font-size: 14px;
}

.control-panel {
  background: white;
  padding: 16px 20px;
  border-bottom: 1px solid #e4e7ed;
}

.graph-container {
  flex: 1;
  position: relative;
  margin: 10px;
  background: white;
  border-radius: 8px;
  overflow: hidden;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  flex-direction: column;
  gap: 16px;
  color: #909399;
}

.loading-icon {
  font-size: 24px;
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.node-connections {
  margin-top: 20px;
}

.node-connections h5 {
  margin: 16px 0 8px 0;
  color: #606266;
}

.node-connections ul {
  padding-left: 20px;
}

.node-connections li {
  margin-bottom: 4px;
  color: #909399;
}

.legend {
  position: absolute;
  top: 20px;
  right: 20px;
  background: rgba(255, 255, 255, 0.9);
  padding: 12px;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.legend h5 {
  margin: 0 0 8px 0;
  color: #606266;
  font-size: 12px;
}

.legend-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}
</style>