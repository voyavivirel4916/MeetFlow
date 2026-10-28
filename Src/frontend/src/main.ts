import { createApp } from 'vue'
import App from './App.vue'
import { createWebHistory } from 'vue-router'
import { createApplicationRouter } from './router'
import { createSession, sessionKey } from './auth/session'
import './style.css'
import './search.css'
import './sample-layout.css'
import './workflow-layout.css'

const session = createSession()
createApp(App).provide(sessionKey, session).use(createApplicationRouter(createWebHistory(), session)).mount('#app')
