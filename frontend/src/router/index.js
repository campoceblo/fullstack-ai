import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Result from '../views/Result.vue'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/result/:jobId',
    name: 'Result',
    component: Result,
    props: true
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router