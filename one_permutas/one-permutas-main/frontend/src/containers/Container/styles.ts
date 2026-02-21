import { styled } from 'styled-components'
import { color } from '../../styles'

export const GlobalContainer = styled.div`
  max-width: 1024px;
  width: 100%;
  background-color: ${color.logoSecundary};
  color: ${color.logoPrimary};
  padding: 24px;
  margin: 0 auto 32px;
  margin-top: 40px;
  border-radius: 4px;
  box-shadow: 1px 1px 3px black;
`

export const Title = styled.h1`
  padding-bottom: 36px;
  background-color: ${color.logoSecundary};
  text-align: center;
`
