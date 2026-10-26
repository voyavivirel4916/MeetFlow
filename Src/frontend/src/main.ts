import { createApp } from 'vue'
import App from './App.vue'
import { createWebHistory } from 'vue-router'
import { createApplicationRouter } from './router'
import './style.css'

createApp(App).use(createApplicationRouter(createWebHistory())).mount('#app')
