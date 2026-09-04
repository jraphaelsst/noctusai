import { createGlobalStyle } from 'styled-components'

export const color = {
  primary: '#2D3436',
  primaryDark: '#1E2426',
  primaryLight: '#4A5568',
  secondary: '#2D3436',
  secondaryLight: '#4A5568',

  success: '#00B894',
  successLight: '#55EFC4',
  warning: '#FDCB6E',
  danger: '#E17055',

  background: '#F8F9FA',
  backgroundDark: '#EDF2F7',
  cardBg: '#FFFFFF',

  text: '#2D3436',
  textLight: '#636E72',
  textMuted: '#B2BEC3',
  textInverse: '#F8F9FA',

  border: '#DFE6E9',
  borderLight: '#EDF2F7',

  shadow: 'rgba(45, 52, 54, 0.06)',
  shadowMedium: 'rgba(45, 52, 54, 0.10)',

  navbar: '#2D3436',
  navbarText: '#F8F9FA',

  main: '#F8F9FA',
  font: '#2D3436',
  bgColor: '#EDF2F7',
  logoPrimary: '#2D3436',
  logoSecundary: '#636E72'
}

export const breakpoints = {
  desktop: '1024px',
  tablet: '768px',
  mobile: '480px',
  smartphone: '450px'
}


export const spacing = {
  xs: '4px',
  sm: '8px',
  md: '16px',
  lg: '24px',
  xl: '32px',
  xxl: '48px'
}

export const radius = {
  sm: '2px',
  md: '2px',
  lg: '2px',
  xl: '4px',
  full: '9999px'
}

export const GlobalCss = createGlobalStyle`
  * {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    list-style: none;
    text-decoration: none;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif;
  }

  html {
    scroll-behavior: smooth;
    width: 100%;
    height: 100%;
    margin: 0;
    padding: 0;
  }

  body {
    background-color: ${color.background};
    color: ${color.text};
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  h1, h2, h3, h4, h5, h6 {
    font-weight: 600;
    line-height: 1.3;
    color: ${color.secondary};
  }

  h1 { font-size: 2rem; }
  h2 { font-size: 1.5rem; }
  h3 { font-size: 1.25rem; }

  @media (max-width: 768px) {
    h1 { font-size: 1.5rem; }
    h2 { font-size: 1.25rem; }
    h3 { font-size: 1.1rem; }
  }

  a {
    color: ${color.primary};
    text-decoration: none;
    transition: color 0.2s ease;
    
    &:hover {
      color: ${color.primaryLight};
      text-decoration: underline;
    }
  }

  button {
    cursor: pointer;
    font-family: inherit;
  }

  input, select, textarea {
    font-family: inherit;
    font-size: 1rem;
  }

  ::selection {
    background: ${color.primary};
    color: ${color.textInverse};
  }

  ::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }

  ::-webkit-scrollbar-track {
    background: ${color.backgroundDark};
  }

  ::-webkit-scrollbar-thumb {
    background: ${color.textMuted};
    border-radius: 4px;
  }

  ::-webkit-scrollbar-thumb:hover {
    background: ${color.textLight};
  }
`
