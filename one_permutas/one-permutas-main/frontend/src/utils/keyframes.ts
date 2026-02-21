import { keyframes } from 'styled-components'

export const fadeInIcon = keyframes`
  0% {
    opacity: 0;
    transform: translate(0%, -150%);
  }
  100% {
    opacity: 1;
    transform: translate(0%, -45%);
  }
`

export const fadeInDropDown = keyframes`
  0% {
    opacity: 0;
    transform: translate(0%, 150%);
  }
  100% {
    opacity: 1;
    transform: translate(0%, 0%);
  }
`

export const fadeInForm = keyframes`
  0% {
    height: 0;
  }
  100% {
    height: 80%;
    padding: 24px;
  }
`

export const fadeInInput = keyframes`
  0% {
    opacity: 0;
  }
  100% {
    opacity: 1;
  }
`
