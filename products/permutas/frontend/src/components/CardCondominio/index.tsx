import {
  Bairro,
  CardContainer,
  Endereco,
  Icons,
  Km,
  Nome,
  Valor
} from './styles'
import { formatCurrency } from '../../utils/formatCurrency'

type Props = {
  nome: string
  bairro: string
  km: string
  endereco: string
  numero: number
  valor_condominio: number
}

const CardCondominio = ({
  nome,
  bairro,
  endereco,
  km,
  numero,
  valor_condominio
}: Props) => {
  return (
    <CardContainer>
      <div>
        <Nome>{nome}</Nome>
        <Bairro>{bairro}</Bairro>
        <Km>{km}</Km>
      </div>
      <div>
        <Endereco>
          {endereco}, {numero}
        </Endereco>
        <Valor>{formatCurrency(valor_condominio)}</Valor>
      </div>
      <Icons>
        <i className="fa-regular fa-pen-to-square" />
        <i className="fa-solid fa-xmark" />
      </Icons>
    </CardContainer>
  )
}

export default CardCondominio
