import {
  Bairro,
  CardContainer,
  Cidade,
  Condominio,
  Corretor,
  Icons,
  Marca,
  Modelo,
  Motor,
  Tipo,
  Valor,
  Zona
} from './styles'

type Props = {
  tipoPermuta: 'imovel' | 'automovel'
  tipo: string
  corretor: string
  valor: number
  condominio?: string
  cidade?: string
  bairro?: string
  zona?: string
  marca?: string
  modelo?: string
  motor?: string
}

const CardCondominio = ({
  tipoPermuta,
  tipo,
  corretor,
  valor,
  condominio,
  cidade,
  bairro,
  zona,
  marca,
  modelo,
  motor
}: Props) => {
  return (
    <CardContainer>
      {tipoPermuta === 'imovel' ? (
        <>
          <div>
            <Tipo>{tipo}</Tipo>
            <Corretor>{corretor}</Corretor>
            <Cidade>{cidade}</Cidade>
            <Bairro>{bairro}</Bairro>
            <Zona>{zona}</Zona>
          </div>
          <div>
            <Condominio>{condominio}</Condominio>
            <Valor>R$ {valor},00</Valor>
          </div>
        </>
      ) : (
        <>
          <div>
            <Tipo>{tipo}</Tipo>
            <Corretor>{corretor}</Corretor>
            <Marca>{marca}</Marca>
            <Modelo>{modelo}</Modelo>
            <Motor>{motor}</Motor>
          </div>
          <div>
            <Valor>R$ {valor},00</Valor>
          </div>
        </>
      )}
      <Icons>
        <i className="fa-regular fa-pen-to-square" />
        <i className="fa-solid fa-xmark" />
      </Icons>
    </CardContainer>
  )
}

export default CardCondominio
