import { styled } from 'styled-components'
import { color } from '../../styles'

export const Container = styled.div`
  border: 0.1px solid ${color.logoPrimary};
  background-color: ${color.logoSecundary};
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 24px 12px;
  border-radius: 4px;
  box-shadow: 1px 1px 4px black;
  position: relative;
  z-index: 1;
  cursor: pointer;

  &.hidden {
    display: none;
  }
`

export const Title = styled.h2``
