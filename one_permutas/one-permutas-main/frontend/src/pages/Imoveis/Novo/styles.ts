import { styled } from 'styled-components'

import { color } from '../../../styles'
import { fadeInForm, fadeInInput } from '../../../utils/keyframes'

export const Form = styled.div`
  background-color: ${color.main};
  margin-top: 0;
  width: 98%;
  margin: 0 auto;
  color: ${color.logoSecundary};
  box-shadow: 1px 1px 4px black;
  margin-top: 2px;
  border-radius: 0 0 4px 4px;
  display: none;
  transition: all 2s ease;
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

export const FormInteresse = styled.div`
  background-color: ${color.main};
  margin-top: 0;
  width: 98%;
  margin: 0 auto;
  color: ${color.logoSecundary};
  box-shadow: 1px 1px 4px black;
  margin-top: 2px;
  border-radius: 0 0 4px 4px;
  display: none;
  transition: all 2s ease;
  position: relative;
  z-index: 0;
  height: 0;
  overflow-y: hidden;
  position: relative;

  &.active {
    display: grid;
    grid-template-columns: 1fr;
    row-gap: 8px;
    justify-items: center;
    animation: ${fadeInForm} 1s ease forwards;
    margin-bottom: 60px;
  }

  p {
    position: absolute;
    bottom: 24px;
    left: 36px;
  }
`

export const FormInput = styled.input`
  border-radius: 4px;
  outline: none;
  border: 1px solid ${color.logoSecundary};
  padding: 4px;
`

export const Select = styled.select`
  border: none;
  border-radius: 4px;
  width: 80px;
  outline: none;
  color: ${color.logoSecundary};
  font-size: 14px;
`

export const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 48px;
`

export const TableHead = styled.th`
  padding: 8px;
`

export const TableRow = styled.tr`
  border-bottom: 1px solid ${color.logoSecundary};

  &:nth-last-child(1) {
    border: none;
  }
`

export const TableCell = styled.td`
  text-align: center;
  padding: 8px;
`

export const TableTitle = styled.h2`
  margin: 24px 0 48px 0;
`
