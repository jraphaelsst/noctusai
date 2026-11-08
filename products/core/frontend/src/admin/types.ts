import type { LazyExoticComponent } from 'react';

export interface AdminRoute {
  path: string;
  component: LazyExoticComponent<any>;
}
