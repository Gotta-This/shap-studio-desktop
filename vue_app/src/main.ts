import { createApp, h } from "vue";
import { ConfigProvider } from "reka-ui";
import { createRouter, createWebHashHistory } from "vue-router";
import App from "./App.vue";
import Workspace from "./views/Workspace.vue";
import Dashboard from "./views/Dashboard.vue";
import Todos from "./views/Todos.vue";
import Inbox from "./views/Inbox.vue";
import WordTool from "./views/WordTool.vue";
import ShapTool from "./views/ShapTool.vue";
import PredictionTool from "./views/PredictionTool.vue";
import CrosstabsTool from "./views/CrosstabsTool.vue";
import MeansTTestTool from "./views/MeansTTestTool.vue";
import DesktopLayoutTool from "./views/DesktopLayoutTool.vue";
import Tools from "./views/Tools.vue";
import Settings from "./views/Settings.vue";
import "./style.css";
import { initializeDisplay } from "./lib/display";
void initializeDisplay();
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", component: Dashboard },
    { path: "/workspace/:id?", component: Workspace },
    { path: "/todos", component: Todos },
    { path: "/inbox", component: Inbox },
    { path: "/tools/word", component: WordTool },
    { path: "/tools/shap", component: ShapTool },
    { path: "/tools/prediction", component: PredictionTool },
    { path: "/tools/crosstabs", component: CrosstabsTool },
    { path: "/tools/means-ttest", component: MeansTTestTool },
    { path: "/tools/desktop-layout", component: DesktopLayoutTool },
    { path: "/tools/:tool", component: Tools },
    { path: "/settings", component: Settings },
  ],
});
// The app scroll container owns scrollbar space; dialogs must not add body padding.
createApp({
  render: () =>
    h(ConfigProvider, { scrollBody: { padding: 0, margin: 0 } }, () => h(App)),
})
  .use(router)
  .mount("#app");
