import { defineConfig } from 'vite';

// 学生端：/index.html；后台管理端：/admin/index.html
export default defineConfig({
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      // 开发环境统一把 /api 转发到本地 FastAPI，避免前端写死后端地址与跨域问题
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      input: {
        student: 'index.html',
        admin: 'admin/index.html',
      },
    },
  },
});
