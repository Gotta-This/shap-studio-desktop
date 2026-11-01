import { createApp } from "vue";
import { createRouter, createWebHashHistory } from "vue-router";
import App from "./App.vue";
import Workspace from "./views/Workspace.vue";
import Dashboard from "./views/Dashboard.vue";
import Todos from "./views/Todos.vue";
import Inbox from "./views/Inbox.vue";
import Tools from "./views/Tools.vue";
import Settings from "./views/Settings.vue";
import "./style.css";
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", component: Dashboard },
    { path: "/workspace/:id?", component: Workspace },
    { path: "/todos", component: Todos },
    { path: "/inbox", component: Inbox },
    { path: "/tools/:tool", component: Tools },
    { path: "/settings", component: Settings },
  ],
});
createApp(App).use(router).mount("#app");
