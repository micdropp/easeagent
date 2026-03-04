import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('./layouts/MainLayout.vue'),
    children: [
      { path: '', name: 'Dashboard', component: () => import('./views/Dashboard.vue') },
      { path: 'devices', name: 'Devices', component: () => import('./views/Devices.vue') },
      { path: 'rooms', name: 'Rooms', component: () => import('./views/Rooms.vue') },
      { path: 'employees', name: 'Employees', component: () => import('./views/Employees.vue') },
      { path: 'agent-logs', name: 'AgentLogs', component: () => import('./views/AgentLogs.vue') },
      { path: 'toilet', name: 'Toilet', component: () => import('./views/Toilet.vue') },
      { path: 'video', name: 'Video', component: () => import('./views/VideoMonitor.vue') },
    ],
  },
]

export default createRouter({ history: createWebHistory(), routes })
