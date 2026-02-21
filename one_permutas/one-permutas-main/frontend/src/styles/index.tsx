import { createGlobalStyle } from 'styled-components'

export const color = {
  main: '#aaa',
  font: '#333',
  bgColor: '#555',

  logoPrimary: 'rgb(180, 149, 86)',
  logoSecundary: 'rgb(54, 64, 68)'
}

export const breakpoints = {
  desktop: '1024px',
  tablet: '768px',
  smartphone: '450px'
}

export const GlobalCss = createGlobalStyle`
  * {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    list-style: none;
    text-decoration: none;
    font-family: 'Raleway', sans-serif;
  }

  body {
    background-color: ${color.main};
    color: ${color.font};
  }
`
