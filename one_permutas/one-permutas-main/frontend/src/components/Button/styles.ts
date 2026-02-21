import { styled } from 'styled-components'

import { color } from '../../styles'

export const ButtonContainer = styled.button`
  padding: 8px 24px 8px 24px;
  margin: 16px 0;
  background-color: transparent;
  border: 0.5px solid ${color.logoPrimary};
  color: ${color.logoPrimary};
  cursor: pointer;
  transition: all 0.3s ease-out;
  width: fit-content;
  box-shadow: 1px 1px 1px black;
  font-weight: bold;
  border-radius: 4px;

  &:hover {
    background-color: ${color.logoPrimary};
    color: ${color.logoSecundary};
    outline: none;
  }
`
