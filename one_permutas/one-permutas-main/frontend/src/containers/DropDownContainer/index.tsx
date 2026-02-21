import { Container } from './styles'

type Props = {
  children: JSX.Element[]
}

const DropDownContainer = ({ children }: Props) => {
  return <Container>{children}</Container>
}

export default DropDownContainer
