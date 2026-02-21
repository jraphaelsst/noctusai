import { styled } from 'styled-components'

import { color } from '../../../styles'
import { fadeInForm, fadeInInput } from '../../../utils/keyframes'

export const Form = styled.form`
  background-color: ${color.main};
  width: 98%;
  margin: 0 auto;
  color: ${color.logoSecundary};
  box-shadow: 1px 1px 4px black;
  margin-top: 2px;
  border-radius: 0 0 4px 4px;
  transition: all 1s ease;
  position: relative;
  z-index: 0;
  height: 0;
  overflow-y: hidden;

  &.active {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    row-gap: 8px;
    justify-items: center;
    animation: ${fadeInForm} 1s ease forwards;
    margin-bottom: 60px;
  }
`

export const FormField = styled.div`
  display: block;

  &.activeInput {
    animation: ${fadeInInput} 1s ease-in;
  }
`

export const FormLabel = styled.p`
  color: ${color.logoSecundary};
  font-size: 15px;
`

export const FormInput = styled.input`
  border-radius: 4px;
  outline: none;
  border: 1px solid ${color.logoSecundary};
  padding: 4px;
`
