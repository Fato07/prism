import { PrismWordmark } from '@/components/prism-wordmark';
import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: <PrismWordmark />,
      transparentMode: 'top',
      url: '/',
    },
    links: [
      {
        text: 'Quickstart',
        url: '/docs/quickstart',
      },
      {
        text: 'CLI',
        url: '/docs/cli',
      },
      {
        text: 'Receipts',
        url: '/docs/receipts',
      },
      {
        text: 'Dashboard',
        url: 'https://prism-dashboard-production-e6e3.up.railway.app',
        external: true,
      },
    ],
  };
}
