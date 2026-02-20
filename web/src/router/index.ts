import { createRouter, createWebHistory } from "vue-router";

import HomeView from "../views/HomeView.vue";
import TaskView from "../views/TaskView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: HomeView },
    { path: "/task/:id", component: TaskView }
  ]
});

export default router;
