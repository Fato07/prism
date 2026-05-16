import { PrismWordmark } from '@/components/prism-wordmark';
import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: <PrismWordmark />,
      transparentMode: 'top',
    },
    links: [
      {
        text: 'Dashboard',
        url: 'https://prism-dashboard-production-e6e3.up.railway.app',
        external: true,
      },
      {
        text: 'CLI',
        url: '/docs/cli',
      },
      {
        text: 'GitHub',
        url: 'https://github.com/Fato07/prism',
        external: true,
      },
    ],
  };
}
