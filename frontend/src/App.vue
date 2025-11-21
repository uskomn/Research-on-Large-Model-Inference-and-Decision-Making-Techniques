<template>
  <div id="app">
    <el-container style="height: 100vh;">
      <!-- 头部 -->
      <el-header style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; display: flex; align-items: center; justify-content: space-between;">
        <div style="display: flex; align-items: center;">
          <el-icon size="24" style="margin-right: 10px;">
            <Medical-Box />
          </el-icon>
          <h2 style="margin: 0;">重症伤员处置问答系统</h2>
        </div>
        <div>
          <el-tag type="success" size="small">专业版</el-tag>
        </div>
      </el-header>

      <!-- 主体内容 -->
      <el-container>
        <!-- 左侧导航 -->
        <el-aside width="250px" style="background-color: #f5f7fa;">
          <el-menu
            :default-active="activeTab"
            @select="handleTabChange"
            style="border: none; height: 100%;"
          >
            <el-menu-item index="chat">
              <el-icon><ChatDotRound /></el-icon>
              <span>问答咨询</span>
            </el-menu-item>
            <el-menu-item index="knowledge">
              <el-icon><Connection /></el-icon>
              <span>知识图谱</span>
            </el-menu-item>
            <el-menu-item index="search">
              <el-icon><Search /></el-icon>
              <span>知识搜索</span>
            </el-menu-item>
          </el-menu>
        </el-aside>

        <!-- 主要内容区域 -->
        <el-main style="padding: 0;">
          <!-- 问答界面 -->
          <div v-if="activeTab === 'chat'" style="height: 100%;">
            <ChatInterface />
          </div>

          <!-- 知识图谱 -->
          <div v-if="activeTab === 'knowledge'" style="height: 100%;">
            <KnowledgeGraph />
          </div>

          <!-- 知识搜索 -->
          <div v-if="activeTab === 'search'" style="height: 100%;">
            <KnowledgeSearch />
          </div>
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script>
import { ref } from 'vue'
import ChatInterface from './views/ChatInterface.vue'
import KnowledgeGraph from './views/KnowledgeGraph.vue'
import KnowledgeSearch from './views/KnowledgeSearch.vue'

export default {
  name: 'App',
  components: {
    ChatInterface,
    KnowledgeGraph,
    KnowledgeSearch
  },
  setup() {
    const activeTab = ref('chat')

    const handleTabChange = (key) => {
      activeTab.value = key
    }

    return {
      activeTab,
      handleTabChange
    }
  }
}
</script>

<style>
#app {
  height: 100vh;
}

.el-menu-item {
  height: 60px;
  line-height: 60px;
}

.el-menu-item.is-active {
  background-color: #e6f7ff;
  border-right: 3px solid #409eff;
}
</style>