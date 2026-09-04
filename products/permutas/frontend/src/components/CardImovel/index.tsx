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
import { formatCurrency } from '../../utils/formatCurrency'

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
        <Valor>{formatCurrency(valor)}</Valor>
      </div>
      <Icons>
        <i className="fa-regular fa-pen-to-square" />
        <i className="fa-solid fa-xmark" />
      </Icons>
    </CardContainer>
  )
}

export default CardImovel
