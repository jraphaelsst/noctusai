import {
  CardContainer,
  Condominio,
  Corretor,
  Icons,
  Ref,
  Tipo,
  Valor
} from './styles'

import { getTipo } from './utils'

type Props = {
  condominio: string
  corretor: string
  referencia: string
  tipo: string
  valor: number
}

const CardImovel = ({
  condominio,
  corretor,
  referencia,
  tipo,
  valor
}: Props) => {
  return (
    <CardContainer>
      <div>
        <Ref>{referencia}</Ref>
        <Corretor>{corretor}</Corretor>
        <Tipo>{getTipo(tipo)}</Tipo>
      </div>
      <div>
        <Condominio>{condominio}</Condominio>
        <Valor>R$ {valor},00</Valor>
      </div>
      <Icons>
        <i className="fa-regular fa-pen-to-square" />
        <i className="fa-solid fa-xmark" />
      </Icons>
    </CardContainer>
  )
}

export default CardImovel
