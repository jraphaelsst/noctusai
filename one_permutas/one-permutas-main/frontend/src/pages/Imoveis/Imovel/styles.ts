import { styled } from 'styled-components'
import { color } from '../../../styles'

export const Container = styled.div`
  width: 100%;
`

export const Banner = styled.div`
  height: 420px;
  width: 100%;
  background-color: ${color.logoPrimary};
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-left: 30px;
`

export const Image = styled.div`
  background-image: url('https://placehold.co/480x360');
  background-repeat: no-repeat;
  height: 360px;
  width: 520px;
`

export const Infos = styled.div`
  height: 360px;
  width: 90%;
  margin: 0 30px 0 30px;
  padding: 24px;
  display: flex;
  justify-content: space-between;
`

export const DescritivoContainer = styled.div`
  display: flex;
  flex-direction: column;
  justify-content: space-between;
`

export const Ref = styled.h1`
  margin-bottom: 24px;
`
export const CorretorTipo = styled.div`
  display: flex;
`

export const Corretor = styled.p`
  margin-right: 16px;
`

export const Tipo = styled.p``

export const Bairro = styled.p`
  margin-bottom: 8px;
`

export const Condominio = styled.p`
  margin-bottom: 8px;
`

export const Endereco = styled.p``

export const Km = styled.p`
  margin-bottom: 8px;
`

export const Proprietario = styled.div`
  margin-top: 8px;
`

export const ProprietarioTitle = styled.h2`
  margin-bottom: 16px;
`

export const Nome = styled.p`
  margin-bottom: 12px;
`

export const Telefone = styled.p`
  margin-bottom: 12px;
`

export const Email = styled.p`
  margin-bottom: 12px;
`

export const Valor = styled.h3`
  margin-bottom: 24px;
`

export const Icons = styled.div`
  i:nth-last-child(1) {
    margin-left: 16px;
  }

  i {
    cursor: pointer;
  }
`

export const Interesses = styled.div``

export const Permutas = styled.div``

export const TituloSecao = styled.h1`
  margin: 48px 0;
`

export const Sections = styled.div`
  text-align: center;
  width: 90%;
  margin: 0 auto;
`
