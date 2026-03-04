<template>
  <el-container class="app-layout">
    <el-aside width="220px" class="app-aside">
      <div class="logo">EaseAgent</div>
      <el-menu
        :default-active="route.path"
        router
        background-color="#1d1e1f"
        text-color="#bbb"
        active-text-color="#409eff"
      >
        <el-menu-item index="/">
          <el-icon><Monitor /></el-icon>
          <span>Dashboard</span>
        </el-menu-item>
        <el-menu-item index="/devices">
          <el-icon><SetUp /></el-icon>
          <span>设备管理</span>
        </el-menu-item>
        <el-menu-item index="/rooms">
          <el-icon><OfficeBuilding /></el-icon>
          <span>房间管理</span>
        </el-menu-item>
        <el-menu-item index="/employees">
          <el-icon><User /></el-icon>
          <span>员工管理</span>
        </el-menu-item>
        <el-menu-item index="/agent-logs">
          <el-icon><Document /></el-icon>
          <span>Agent 日志</span>
        </el-menu-item>
        <el-menu-item index="/toilet">
          <el-icon><Place /></el-icon>
          <span>厕位状态</span>
        </el-menu-item>
        <el-menu-item index="/video">
          <el-icon><VideoCamera /></el-icon>
          <span>视频监控</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="app-header">
        <span class="header-title">{{ route.meta.title ?? route.name }}</span>
        <el-tag :type="wsConnected ? 'success' : 'danger'" size="small">
          WS {{ wsConnected ? '已连接' : '断开' }}
        </el-tag>
      </el-header>

      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useWebSocket } from '../composables/useWebSocket'
import {
  Monitor, SetUp, OfficeBuilding, User,
  Document, Place, VideoCamera,
} from '@element-plus/icons-vue'

const route = useRoute()
const { connected: wsConnected } = useWebSocket()
</script>

<style>
html, body, #app { margin: 0; padding: 0; height: 100%; }
.app-layout { height: 100vh; }
.app-aside {
  background: #1d1e1f;
  overflow-y: auto;
  border-right: 1px solid #333;
}
.logo {
  height: 56px; display: flex; align-items: center; justify-content: center;
  font-size: 20px; font-weight: 700; color: #409eff;
  letter-spacing: 2px; border-bottom: 1px solid #333;
}
.app-header {
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid #eee; background: #fff;
}
.header-title { font-size: 16px; font-weight: 600; }
.app-main { background: #f5f7fa; }
</style>
