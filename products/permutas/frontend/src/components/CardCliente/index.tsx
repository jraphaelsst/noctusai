import { CardContainer, Corretor, Email, Icons, Nome, Telefone } from './styles'

type Props = {
  corretor: string
  nome: string
  telefone: string
  email: string
}

const CardCliente = ({ corretor, nome, telefone, email }: Props) => {
  return (
    <CardContainer>
      <div>
        <Nome>{nome}</Nome>
        <Corretor>{corretor}</Corretor>
      </div>
      <div>
        <Telefone>{telefone}</Telefone>
        <Email>{email}</Email>
      </div>
      <Icons>
        <i className="fa-regular fa-pen-to-square" />
        <i className="fa-solid fa-xmark" />
      </Icons>
    </CardContainer>
  )
}

export default CardCliente
