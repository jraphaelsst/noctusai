import { Container, Title } from './styles'

type Props = {
  id: string
  title: string
  className?: string
}

const DropDown = ({ id, title, className }: Props) => {
  return (
    <Container id={id} className={className}>
      <Title>{title}</Title>
    </Container>
  )
}

export default DropDown
