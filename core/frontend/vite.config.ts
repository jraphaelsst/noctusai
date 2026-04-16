import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@noctusai/shared': path.resolve(__dirname, '../../seed/lib/frontend/src'),
      // Shared design-system imports these packages — resolve from this project
      'lucide-react': path.resolve(__dirname, 'node_modules/lucide-react'),
      '@radix-ui/react-hover-card': path.resolve(__dirname, 'node_modules/@radix-ui/react-hover-card'),
      '@radix-ui/react-collapsible': path.resolve(__dirname, 'node_modules/@radix-ui/react-collapsible'),
    },
    dedupe: ['react', 'react-dom'],
  },
});
