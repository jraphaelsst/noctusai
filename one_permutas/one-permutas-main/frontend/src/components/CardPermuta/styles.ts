import { styled } from 'styled-components'

import { color } from '../../styles'

export const CardContainer = styled.div`
  position: relative;
  height: fit-content;
  width: 300px;
  background-color: ${color.bgColor};
  padding: 24px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  border-radius: 8px;
  box-shadow: 1px 1px 4px black;
  transition: all 0.2s ease;

  &:hover {
    transform: scale(1.05);
  }
`

export const Icons = styled.div`
  position: absolute;
  top: 8px;
  right: 8px;

  i:nth-last-child(1) {
    margin-left: 8px;
  }

  i {
    cursor: pointer;
  }
`

export const Tipo = styled.h2`
  margin-bottom: 8px;
`

export const Condominio = styled.h3`
  margin-bottom: 8px;
`

export const Corretor = styled.p`
  margin-bottom: 24px;
`

export const Cidade = styled.p``

export const Bairro = styled.p``

export const Zona = styled.p``

export const Valor = styled.div`
  margin-bottom: 8px;
`

export const Marca = styled.p``

export const Modelo = styled.p``

export const Motor = styled.p``
