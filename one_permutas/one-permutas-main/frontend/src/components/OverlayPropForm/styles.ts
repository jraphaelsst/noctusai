import { styled } from 'styled-components'

import { color } from '../../styles'
import {
  FormField,
  FormInput,
  FormLabel
} from '../../pages/Imoveis/Novo/styles'

export const OverlayContainer = styled.div`
  position: fixed;
  display: flex;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 999;
  display: none;

  &.isOpen {
    display: flex;
  }

  ${FormField} {
    margin-top: 16px;
    ${FormLabel} {
      color: ${color.logoPrimary};
    }
    ${FormInput} {
      box-shadow: 0 0 2px black;
    }
  }
`

export const FormContainer = styled.div`
  position: fixed;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: fit-content;
  width: 30%;
  top: 25%;
  left: 35%;
  background-color: ${color.logoSecundary};
  z-index: 1000;
  color: ${color.logoPrimary};
  border-radius: 4px;
  box-shadow: 0 0 2px black;
  padding: 16px 0;
`

export const Overlay = styled.div`
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  opacity: 0.6;
  background-color: black;
  z-index: 998;
`

export const Title = styled.h2``
